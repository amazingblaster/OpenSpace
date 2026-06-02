"""Model-call and model-response control flow for GroundingAgent turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openspace.agents.turns import events as turn_events
from openspace.agents.turns.compaction_controller import persist_compacted_session_messages
from openspace.agents.turns import session_policy, stop_policy
from openspace.agents.turns.context import TurnControllerContext
from openspace.llm.errors import (
    CannotRetryError,
    FallbackTriggeredError,
    PromptTooLongError,
    classify_api_error,
    get_error_message_for_user,
    is_abort_error,
)
from openspace.llm.types import ModelResponse
from openspace.services.conversation.compact import (
    build_post_compact_messages,
    compact_conversation,
    run_post_compact_cleanup,
)
from openspace.services.session.recovery import recover_conversation
from openspace.services.conversation.messages import (
    build_assistant_api_error_message,
    build_user_interruption_message,
)
from openspace.utils.logging import Logger

logger = Logger.get_logger(__name__)

@dataclass(slots=True)
class ModelCallResult:
    action: str
    messages: list[dict[str, Any]]
    model_response: ModelResponse | None = None


@dataclass(slots=True)
class ModelResponseResult:
    action: str
    messages: list[dict[str, Any]]
    has_tool_calls: bool = False
    assistant_content: Any = ""


async def call_model_with_recovery(
    turn: TurnControllerContext,
    *,
    messages: list[dict[str, Any]],
    active_tools: list[Any],
) -> ModelCallResult:
    """Call the LLM and handle retryable model-side failures."""

    agent = turn.agent
    context = turn.context
    tool_use_context = turn.tool_use_context
    state = turn.state
    state.refresh_reasoning_effort(tool_use_context)
    model_response: ModelResponse | None = None
    try:
        marker = getattr(turn.low_latency_profiler, "mark", None)
        if callable(marker):
            if state.current_iteration == 1:
                marker("first_model_request", iteration=state.current_iteration)
            marker("llm.request_start", iteration=state.current_iteration)
        with turn.span("llm.request", iteration=state.current_iteration):
            model_response = await agent._llm_client.call_model(
                messages=messages,
                tools=active_tools if context.get("auto_execute", True) else None,
                abort_event=turn.abort_event,
                model=state.effective_model,
                fallback_model=state.effective_fallback_model,
                reasoning_effort=state.effective_reasoning_effort,
                tool_prompt_context=tool_use_context,
            )
        if callable(marker) and model_response is not None:
            marker(
                "llm.first_chunk",
                iteration=state.current_iteration,
                streaming=True,
            )
        return ModelCallResult(
            action="response",
            messages=messages,
            model_response=model_response,
        )

    except PromptTooLongError as ptl_err:
        logger.warning("Prompt too long, attempting compact: %s", ptl_err)
        await tool_use_context.emit_event(
            "compact_start",
            {"trigger": "prompt_too_long"},
        )
        try:
            compaction = await compact_conversation(
                messages,
                agent._llm_client,
                tool_use_context,
                is_auto_compact=True,
                hook_registry=agent._hook_registry,
                model=state.effective_model,
                emit_lifecycle_events=False,
            )
            post_msgs = build_post_compact_messages(compaction)
            run_post_compact_cleanup(tool_use_context)
            system_msgs = agent._refresh_system_messages_after_compact(
                messages,
                cwd=context.get("workspace_dir"),
                deferred_tool_names=tool_use_context.deferred_tool_names,
                memory_mode=tool_use_context.memory_mode,
                skills_enabled=not tool_use_context.skills_disabled,
                skill_discovery_enabled=agent._has_discover_skills_tool(
                    tool_use_context.tools
                ),
                permission_mode=tool_use_context.permission_mode,
                plan_file_path=tool_use_context.plan_file_path,
                response_style=tool_use_context.response_style,
                coordinator_mode=tool_use_context.coordinator_mode,
                coordinator_mode_enabled=tool_use_context.coordinator_mode_enabled,
            )
            messages = system_msgs + post_msgs
            await persist_compacted_session_messages(
                agent,
                tool_use_context,
                messages,
                model=state.effective_model,
            )
            agent._sync_tool_use_context_runtime(
                tool_use_context,
                messages=messages,
            )
            state.compact_tracking.compacted = True
            state.compact_tracking.consecutive_failures = 0
            await tool_use_context.emit_event("compact_complete", {"success": True})
            logger.info("PTL recovery compact succeeded, retrying call_model")
            return ModelCallResult(action="retry", messages=messages)
        except Exception as compact_err:
            state.compact_tracking.consecutive_failures += 1
            logger.warning(
                "PTL compact failed (%s), stopping without local truncation",
                state.compact_tracking.consecutive_failures,
            )
            await tool_use_context.emit_event(
                "compact_complete",
                {
                    "success": False,
                    "error": str(compact_err),
                },
            )
            error_msg = get_error_message_for_user(
                ptl_err,
                state.effective_model,
            )
            messages.append(
                build_assistant_api_error_message(
                    error_msg,
                    error_details=(
                        f"{ptl_err}; compact_error={compact_err}"
                    ),
                )
            )
            agent._sync_tool_use_context_runtime(
                tool_use_context,
                messages=messages,
            )
            state.stop_reason_final = "prompt_too_long"
            return ModelCallResult(action="break", messages=messages)

    except FallbackTriggeredError as fb_err:
        logger.warning(
            "Fallback triggered: %s -> %s (task-local switch only, shared "
            "LLMClient unchanged)",
            fb_err.original_model,
            fb_err.fallback_model,
        )
        current_model = state.effective_model
        fallback_model = str(fb_err.fallback_model or "").strip()
        if not fallback_model or fallback_model == current_model:
            messages.append(
                build_assistant_api_error_message(
                    get_error_message_for_user(
                        fb_err,
                        current_model or "unknown",
                    ),
                    error_details=str(fb_err),
                )
            )
            agent._sync_tool_use_context_runtime(
                tool_use_context,
                messages=messages,
            )
            state.stop_reason_final = "model_error"
            return ModelCallResult(action="break", messages=messages)

        state.switch_to_fallback(fallback_model)
        agent._sync_tool_use_context_runtime(
            tool_use_context,
            model=state.effective_model,
        )
        return ModelCallResult(action="retry", messages=messages)

    except CannotRetryError as cr_err:
        recovery = recover_conversation(messages, cr_err)
        messages = recovery.messages
        agent._sync_tool_use_context_runtime(
            tool_use_context,
            messages=messages,
        )
        if recovery.should_retry and state.conversation_recovery_retry_count < 1:
            state.conversation_recovery_retry_count += 1
            await tool_use_context.emit_event(
                "conversation_recovery",
                {
                    "reason": recovery.reason,
                    "retry": True,
                    "attempt": state.conversation_recovery_retry_count,
                    "dropped_messages": recovery.dropped_messages,
                    "inserted_synthetic_results": (
                        recovery.inserted_synthetic_results
                    ),
                    "error": classify_api_error(cr_err.original_error or cr_err),
                },
            )
            logger.info(
                "Conversation recovery retrying last turn after %s",
                classify_api_error(cr_err.original_error or cr_err),
            )
            return ModelCallResult(action="retry", messages=messages)

        error_msg = get_error_message_for_user(
            cr_err.original_error or cr_err,
            state.effective_model,
        )
        messages.append(
            build_assistant_api_error_message(
                error_msg,
                error_details=str(cr_err),
            )
        )
        agent._sync_tool_use_context_runtime(tool_use_context, messages=messages)
        await session_policy.save_after_model_error(
            agent,
            tool_use_context,
            messages,
            model=state.effective_model,
        )
        state.stop_reason_final = "model_error"
        return ModelCallResult(action="break", messages=messages)

    except Exception as api_err:
        if is_abort_error(api_err):
            messages.append(build_user_interruption_message(tool_use=False))
            agent._sync_tool_use_context_runtime(
                tool_use_context,
                messages=messages,
            )
            state.stop_reason_final = "aborted"
            return ModelCallResult(action="break", messages=messages)
        recovery = recover_conversation(messages, api_err)
        messages = recovery.messages
        agent._sync_tool_use_context_runtime(
            tool_use_context,
            messages=messages,
        )
        if recovery.should_retry and state.conversation_recovery_retry_count < 1:
            state.conversation_recovery_retry_count += 1
            await tool_use_context.emit_event(
                "conversation_recovery",
                {
                    "reason": recovery.reason,
                    "retry": True,
                    "attempt": state.conversation_recovery_retry_count,
                    "dropped_messages": recovery.dropped_messages,
                    "inserted_synthetic_results": (
                        recovery.inserted_synthetic_results
                    ),
                    "error": classify_api_error(api_err),
                },
            )
            logger.info(
                "Conversation recovery retrying last turn after %s",
                classify_api_error(api_err),
            )
            return ModelCallResult(action="retry", messages=messages)
        error_msg = get_error_message_for_user(api_err, state.effective_model)
        messages.append(
            build_assistant_api_error_message(
                error_msg,
                error_details=str(api_err),
            )
        )
        agent._sync_tool_use_context_runtime(tool_use_context, messages=messages)
        await session_policy.save_after_model_error(
            agent,
            tool_use_context,
            messages,
            model=state.effective_model,
        )
        state.stop_reason_final = "model_error"
        logger.error(
            "call_model failed: %s - %s",
            classify_api_error(api_err),
            api_err,
        )
        return ModelCallResult(action="break", messages=messages)


async def handle_model_response(
    turn: TurnControllerContext,
    *,
    model_response: ModelResponse | None,
    messages: list[dict[str, Any]],
) -> ModelResponseResult:
    """Append and classify a model response before any tool execution."""

    agent = turn.agent
    context = turn.context
    tool_use_context = turn.tool_use_context
    state = turn.state
    if model_response is None:
        state.consecutive_empty += 1
        if state.current_iteration >= state.max_iterations:
            state.stop_reason_final = "max_turns"
            return ModelResponseResult(action="break", messages=messages)
        if state.consecutive_empty >= state.max_consecutive_empty:
            state.stop_reason_final = "empty_response"
            return ModelResponseResult(action="break", messages=messages)
        return ModelResponseResult(action="continue", messages=messages)

    messages.append(model_response.assistant_message)
    state.budget_tracker.record_usage(model_response.usage)
    agent._sync_tool_use_context_runtime(tool_use_context, messages=messages)
    await session_policy.save_after_assistant_response(
        agent,
        tool_use_context,
        messages,
        usage=model_response.usage,
        model=state.effective_model,
    )

    abort_stop_reason = stop_policy.abort_stop_reason(
        turn.abort_event,
        after_model_response=True,
    )
    if abort_stop_reason:
        messages.append(build_user_interruption_message(tool_use=False))
        agent._sync_tool_use_context_runtime(tool_use_context, messages=messages)
        state.stop_reason_final = abort_stop_reason
        return ModelResponseResult(action="break", messages=messages)

    response_followups = agent._get_model_response_followup_messages(
        model_response
    )
    has_model_api_error = agent._is_api_error_message(
        model_response.assistant_message
    ) or any(agent._is_api_error_message(message) for message in response_followups)

    assistant_content = model_response.assistant_message.get("content", "")
    has_tool_calls = bool(model_response.tool_calls)
    has_assistant_text = (
        assistant_content
        and isinstance(assistant_content, str)
        and assistant_content.strip()
    )

    if (
        not has_assistant_text
        and not has_tool_calls
        and model_response.stop_reason == "length"
    ):
        if state.current_iteration >= state.max_iterations:
            state.consecutive_empty += 1
            state.stop_reason_final = "max_turns"
            return ModelResponseResult(
                action="break",
                messages=messages,
                has_tool_calls=has_tool_calls,
                assistant_content=assistant_content,
            )
        if stop_policy.should_recover_max_output_tokens(
            stop_reason=model_response.stop_reason,
            has_tool_calls=has_tool_calls,
            recovery_count=state.max_output_tokens_recovery_count,
        ):
            state.max_output_tokens_recovery_count += 1
            messages.append(
                stop_policy.build_max_output_tokens_recovery_message(
                    state.max_output_tokens_recovery_count
                )
            )
            agent._sync_tool_use_context_runtime(
                tool_use_context,
                messages=messages,
            )
            logger.info(
                "max_output_tokens recovery %s",
                state.max_output_tokens_recovery_count,
            )
            return ModelResponseResult(
                action="continue",
                messages=messages,
                has_tool_calls=has_tool_calls,
                assistant_content=assistant_content,
            )
        logger.warning("max_output_tokens recovery limit reached")
        state.stop_reason_final = "max_output_tokens"
        return ModelResponseResult(
            action="break",
            messages=messages,
            has_tool_calls=has_tool_calls,
            assistant_content=assistant_content,
        )

    if has_assistant_text:
        state.consecutive_empty = 0
        await agent._emit_runtime_event(
            "agent_output",
            turn_events.agent_output_payload(
                agent,
                context,
                agent_id=turn.agent_id,
                content=assistant_content,
                iteration=state.current_iteration,
                tool_calls_count=len(model_response.tool_calls),
            ),
        )
    elif not has_tool_calls:
        state.consecutive_empty += 1
        logger.warning(
            "Empty response %s/%s",
            state.consecutive_empty,
            state.max_consecutive_empty,
        )
        if state.current_iteration >= state.max_iterations:
            state.stop_reason_final = "max_turns"
            return ModelResponseResult(
                action="break",
                messages=messages,
                has_tool_calls=has_tool_calls,
                assistant_content=assistant_content,
            )
        if state.consecutive_empty >= state.max_consecutive_empty:
            logger.error("Too many consecutive empty responses")
            state.stop_reason_final = "empty_response"
            return ModelResponseResult(
                action="break",
                messages=messages,
                has_tool_calls=has_tool_calls,
                assistant_content=assistant_content,
            )
        return ModelResponseResult(
            action="continue",
            messages=messages,
            has_tool_calls=has_tool_calls,
            assistant_content=assistant_content,
        )
    elif stop_policy.is_tool_call_only_response(
        assistant_content=assistant_content,
        has_tool_calls=has_tool_calls,
    ):
        state.consecutive_empty = 0
    else:
        state.consecutive_empty = 0

    if has_model_api_error:
        if stop_policy.should_recover_max_output_tokens(
            stop_reason=model_response.stop_reason,
            has_tool_calls=has_tool_calls,
            recovery_count=state.max_output_tokens_recovery_count,
        ):
            state.max_output_tokens_recovery_count += 1
            messages.append(
                stop_policy.build_max_output_tokens_recovery_message(
                    state.max_output_tokens_recovery_count
                )
            )
            agent._sync_tool_use_context_runtime(
                tool_use_context,
                messages=messages,
            )
            logger.info(
                "max_output_tokens recovery %s",
                state.max_output_tokens_recovery_count,
            )
            return ModelResponseResult(
                action="continue",
                messages=messages,
                has_tool_calls=has_tool_calls,
                assistant_content=assistant_content,
            )

        if response_followups:
            messages.extend(response_followups)
            agent._sync_tool_use_context_runtime(
                tool_use_context,
                messages=messages,
            )
        state.stop_reason_final = agent._model_error_stop_reason(
            model_response.stop_reason
        )
        return ModelResponseResult(
            action="break",
            messages=messages,
            has_tool_calls=has_tool_calls,
            assistant_content=assistant_content,
        )

    if not has_tool_calls:
        if model_response.stop_reason == "length":
            if stop_policy.should_recover_max_output_tokens(
                stop_reason=model_response.stop_reason,
                has_tool_calls=has_tool_calls,
                recovery_count=state.max_output_tokens_recovery_count,
            ):
                state.max_output_tokens_recovery_count += 1
                messages.append(
                    stop_policy.build_max_output_tokens_recovery_message(
                        state.max_output_tokens_recovery_count
                    )
                )
                agent._sync_tool_use_context_runtime(
                    tool_use_context,
                    messages=messages,
                )
                logger.info(
                    "max_output_tokens recovery %s",
                    state.max_output_tokens_recovery_count,
                )
                return ModelResponseResult(
                    action="continue",
                    messages=messages,
                    has_tool_calls=has_tool_calls,
                    assistant_content=assistant_content,
                )
            logger.warning("max_output_tokens recovery limit reached")
            state.stop_reason_final = "max_output_tokens"
            return ModelResponseResult(
                action="break",
                messages=messages,
                has_tool_calls=has_tool_calls,
                assistant_content=assistant_content,
            )

        from openspace.services.tooling.stop import handle_stop_hooks

        stop_hook_result = await handle_stop_hooks(
            messages=messages,
            last_response=model_response,
            context=tool_use_context,
        )
        if stop_hook_result.blocking_errors:
            messages.extend(stop_hook_result.blocking_errors)
            agent._sync_tool_use_context_runtime(
                tool_use_context,
                messages=messages,
            )
            logger.info(
                "Stop hook blocking - continuing with injected messages"
            )
            return ModelResponseResult(
                action="continue",
                messages=messages,
                has_tool_calls=has_tool_calls,
                assistant_content=assistant_content,
            )
        if stop_hook_result.prevent_continuation:
            state.stop_reason_final = "stop_hook_prevented"
            return ModelResponseResult(
                action="break",
                messages=messages,
                has_tool_calls=has_tool_calls,
                assistant_content=assistant_content,
            )

        budget_decision = state.budget_tracker.check(
            agent_id=None if turn.agent_id == "primary" else turn.agent_id,
            budget=state.current_turn_token_budget,
        )
        if budget_decision.action == "continue":
            await tool_use_context.emit_event(
                "token_budget_continue",
                {
                    "continuation_count": budget_decision.continuation_count,
                    "pct": budget_decision.pct,
                    "turn_tokens": budget_decision.turn_tokens,
                    "budget": budget_decision.budget,
                },
            )
            messages.append(
                {
                    "role": "user",
                    "content": budget_decision.nudge_message or "",
                    "_meta": {
                        "type": "token_budget_continuation",
                        "is_meta": True,
                    },
                }
            )
            agent._sync_tool_use_context_runtime(
                tool_use_context,
                messages=messages,
            )
            state.reset_max_output_recovery()
            logger.info(
                "Token budget continuation #%s: %s%% (%s / %s)",
                budget_decision.continuation_count,
                budget_decision.pct,
                budget_decision.turn_tokens,
                budget_decision.budget,
            )
            return ModelResponseResult(
                action="continue",
                messages=messages,
                has_tool_calls=has_tool_calls,
                assistant_content=assistant_content,
            )

        if budget_decision.completion_event is not None:
            event_payload = budget_decision.completion_event.to_dict()
            await tool_use_context.emit_event(
                "token_budget_completed",
                event_payload,
            )
            if budget_decision.completion_event.diminishing_returns:
                logger.info(
                    "Token budget early stop: diminishing returns at %s%%",
                    budget_decision.completion_event.pct,
                )

        state.stop_reason_final = "completed"
        return ModelResponseResult(
            action="break",
            messages=messages,
            has_tool_calls=has_tool_calls,
            assistant_content=assistant_content,
        )

    return ModelResponseResult(
        action="tools",
        messages=messages,
        has_tool_calls=True,
        assistant_content=assistant_content,
    )

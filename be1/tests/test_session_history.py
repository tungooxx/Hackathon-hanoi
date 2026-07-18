from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from langgraph.checkpoint.memory import InMemorySaver

from app.graph import build_graph
from app.schemas import IntentResult
from app.session_history import (
    append_message,
    mock_markdown_summary,
    render_session_context,
)


class SessionHistoryFormattingTests(unittest.TestCase):
    def test_context_is_summary_followed_by_recent_messages(self) -> None:
        context = render_session_context(
            "# Session context\n\n- Previously discussed air conditioners.",
            [
                {"role": "user", "content": "U3: Tư vấn máy giặt"},
                {
                    "role": "assistant",
                    "content": "A3: Anh/chị cần máy bao nhiêu kg?",
                },
                {"role": "user", "content": "U4: Khoảng 10 kg"},
            ],
        )

        self.assertLess(context.index("Previously discussed"), context.index("U3"))
        self.assertLess(context.index("U3"), context.index("A3"))
        self.assertLess(context.index("A3"), context.index("U4"))

    def test_compressed_messages_are_replaced_by_fresh_topic_window(self) -> None:
        old_window = [
            {"role": "user", "content": "U1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "U2"},
            {"role": "assistant", "content": "A2"},
        ]

        compressed = mock_markdown_summary("", old_window)
        fresh_window = append_message([], role="user", content="U3")
        context = render_session_context(compressed, fresh_window)

        self.assertTrue(context.startswith("## Compressed session context"))
        self.assertTrue(
            all(turn in compressed for turn in ("U1", "A1", "U2", "A2"))
        )
        self.assertEqual(context.count("U3"), 1)
        self.assertGreater(context.rfind("U3"), context.rfind("A2"))


class SessionHistoryGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_topic_change_compresses_old_window_before_new_turn(self) -> None:
        intents = AsyncMock(side_effect=[
            IntentResult(intent_type="new_topic", category="Máy lạnh"),
            IntentResult(intent_type="same_topic", category="Máy lạnh"),
            IntentResult(intent_type="new_topic", category="Máy giặt"),
            IntentResult(intent_type="same_topic", category="Máy giặt"),
        ])
        resolve_category = AsyncMock(side_effect=[
            "Máy lạnh",
            None,
            "Máy giặt",
            None,
        ])
        get_products = AsyncMock(return_value=[])
        summarize = AsyncMock(return_value="# Session context\n\n- C1")
        phrase_contexts: list[str] = []
        response_number = 0

        async def stream_phrase(_kind: str, context: dict):
            nonlocal response_number
            response_number += 1
            phrase_contexts.append(context["history_context"])
            yield f"A{response_number}"

        graph = build_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "history-test"}}

        with (
            patch("app.graph.llm.extract_intent", intents),
            patch(
                "app.graph.product_repo.resolve_category",
                resolve_category,
            ),
            patch("app.graph.product_repo.get_products", get_products),
            patch(
                "app.graph.llm.summarize_session_history",
                summarize,
            ),
            patch("app.graph.llm.stream_phrase", stream_phrase),
        ):
            await self._run_turn(graph, config, "U1", "")
            await self._run_turn(graph, config, "U2", "")
            topic_change_events = await self._run_turn(
                graph,
                config,
                "U3",
                "",
            )
            await self._run_turn(
                graph,
                config,
                "U4",
                "# Session context\n\n- C1",
            )

        compressed_messages = summarize.await_args.args[1]
        self.assertEqual(
            [(item["role"], item["content"]) for item in compressed_messages],
            [
                ("user", "U1"),
                ("assistant", "A1"),
                ("user", "U2"),
                ("assistant", "A2"),
            ],
        )
        self.assertIn(
            {
                "type": "_session_content_update",
                "content": "# Session context\n\n- C1",
            },
            topic_change_events,
        )
        self.assertIn("- C1", phrase_contexts[2])
        self.assertIn("U3", phrase_contexts[2])
        self.assertNotIn("U2", phrase_contexts[2])
        self.assertLess(phrase_contexts[3].index("- C1"), phrase_contexts[3].index("U3"))
        self.assertLess(phrase_contexts[3].index("U3"), phrase_contexts[3].index("A3"))
        self.assertLess(phrase_contexts[3].index("A3"), phrase_contexts[3].index("U4"))

        state = await graph.aget_state(config)
        self.assertEqual(state.values["session_content"], "# Session context\n\n- C1")
        self.assertEqual(
            [
                (item["role"], item["content"])
                for item in state.values["recent_messages"]
            ],
            [
                ("user", "U3"),
                ("assistant", "A3"),
                ("user", "U4"),
                ("assistant", "A4"),
            ],
        )

    @staticmethod
    async def _run_turn(graph, config: dict, message: str, session_content: str):
        return [
            event
            async for event in graph.astream(
                {
                    "user_input": message,
                    "session_content": session_content,
                },
                config,
                stream_mode="custom",
            )
        ]


if __name__ == "__main__":
    unittest.main()

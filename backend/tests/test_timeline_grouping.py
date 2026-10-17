"""Contextual timeline regressions using CI's lightweight model stubs."""

import json
import types
import unittest
from unittest.mock import Mock, patch

from test_timeline_grounding import load_generator
from app.base_models.timeline_models import TimelineCategory, TimelineSourceSegment
from app.functions.timeline import timeline_ai as ai


class TimelineGroupingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = load_generator()

    @staticmethod
    def segment(text, start=0, end=5):
        return TimelineSourceSegment(text=text, speaker="DM", start_time=start, end_time=end)

    def test_related_segments_are_combined_into_one_group(self):
        segments = [
            self.segment("You discover a locked chest.", 10, 13),
            self.segment("I walk over to it.", 14, 16),
            self.segment("I open the chest.", 17, 19),
        ]
        with patch.object(self.generator, '_detect_segment_category', side_effect=[
            TimelineCategory.discovery, TimelineCategory.dialogue, TimelineCategory.discovery,
        ]):
            self.assertEqual(self.generator._group_segments(segments), [segments])

    def test_large_gap_still_splits_groups(self):
        segments = [self.segment("You discover a locked chest.", 10, 13),
                    self.segment("I open the chest.", 50, 53)]
        with patch.object(self.generator, '_detect_segment_category',
                          return_value=TimelineCategory.discovery):
            self.assertEqual(self.generator._group_segments(segments), [[s] for s in segments])

    def test_distinct_meaningful_categories_still_split(self):
        segments = [self.segment("We discover the hidden cave.", 0, 10),
                    self.segment("We attack the dragon.", 10, 20)]
        with patch.object(self.generator, '_detect_segment_category', side_effect=[
            TimelineCategory.discovery, TimelineCategory.combat,
        ]):
            self.assertEqual(self.generator._group_segments(segments), [[s] for s in segments])

    def test_duration_includes_incoming_end_and_has_no_segment_count_cap(self):
        segments = [self.segment("We continued along the road.", i * 10, (i + 1) * 10)
                    for i in range(12)]
        incoming = self.segment("We continued along the road.", 120, 150)
        with patch.object(self.generator, '_detect_segment_category',
                          return_value=TimelineCategory.travel):
            self.assertEqual(self.generator._group_segments(segments + [incoming]),
                             [segments, [incoming]])

    def test_boundary_still_splits_same_category(self):
        segments = [self.segment("We crossed the river.", 0, 10),
                    self.segment("Later we crossed the bridge.", 10, 20)]
        with patch.object(self.generator, '_detect_segment_category',
                          return_value=TimelineCategory.travel):
            self.assertEqual(self.generator._group_segments(segments), [[s] for s in segments])
        self.assertEqual(self.generator._group_segments([]), [])


class ContextualTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = load_generator()

    def setUp(self):
        self.enterContext(patch.object(ai, 'TIMELINE_AI_ENABLED', True))
        self.enterContext(patch.object(self.generator, 'semantic_event_decision',
            return_value=types.SimpleNamespace(keep=True, non_event_score=0.1, margin=0.5)))

    @staticmethod
    def row(index, text, **overrides):
        row = dict(id=index, keep=True, occurred=True, importance=0.9,
                   category='discovery', evidence=text, locations=[], temporal_entities=[])
        row.update(overrides)
        return row

    @staticmethod
    def response(rows):
        response = Mock()
        response.json.return_value = {'message': {'content': json.dumps({'results': rows})}}
        return response

    def generate(self, texts):
        groups = [[TimelineGroupingTests.segment(text, i * 150, i * 150 + 5)]
                  for i, text in enumerate(texts)]
        self.enterContext(patch.object(self.generator, 'get_all_transcription_documents',
                                       return_value=[]))
        self.enterContext(patch.object(self.generator, '_expand_documents_into_segments',
                                       return_value=[group[0] for group in groups]))
        self.enterContext(patch.object(self.generator, '_group_segments', return_value=groups))
        return self.generator.generate_timeline_from_embeddings()

    def test_context_includes_filtered_neighbors_but_cannot_supply_evidence_or_entities(self):
        previous = "You discover an ancient chest in Waterdeep at dawn."
        current = "I open it."
        following = "Inside is a legendary sword."
        def semantic(text):
            return types.SimpleNamespace(keep=False,
                non_event_score=0.4 if text == current else 0.9,
                margin=-0.1 if text == current else -0.4)
        with patch.object(self.generator, 'semantic_event_decision', side_effect=semantic), \
             patch.object(ai.requests, 'post', return_value=self.response([
                 self.row(0, current, locations=['Waterdeep'], temporal_entities=['at dawn']),
             ])) as post:
            events, count = self.generate([previous, current, following])
        self.assertEqual(count, 3)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, current)
        self.assertEqual(events[0].category, TimelineCategory.discovery)
        self.assertEqual([s.text for s in events[0].source_segments], [current])
        self.assertEqual(events[0].locations, [])
        self.assertEqual(events[0].temporal_entities, [])
        post.assert_called_once()
        payload = post.call_args.kwargs['json']
        items = json.loads(payload['messages'][1]['content'])
        self.assertEqual(items, [dict(id=0, transcript=current, speakers='DM',
                                     previous=previous, following=following)])
        for label in ['PREVIOUS', 'CURRENT', 'FOLLOWING']:
            self.assertIn(label, payload['messages'][0]['content'])

    def test_contextual_category_is_used_without_second_llm_or_local_classification(self):
        for category, text in [
            ('discovery', 'I open it.'), ('item', 'I take it.'),
            ('combat', 'I strike him.'), ('travel', 'We made it.'),
        ]:
            with self.subTest(category=category), \
                 patch.object(self.generator, '_detect_category',
                              side_effect=AssertionError('redundant classification')), \
                 patch.object(ai.requests, 'post', return_value=self.response([
                     self.row(0, text, category=category),
                 ])) as post:
                events, count = self.generate([text])
                self.assertEqual(count, 1)
                self.assertEqual(events[0].category.value, category)
                self.assertEqual(events[0].title, text)
                post.assert_called_once()

    def test_context_cannot_borrow_or_fabricate_event_evidence(self):
        text = 'The guard mentioned the silver key.'
        adjacent = 'Aria received the silver key in Waterdeep.'
        for evidence in [adjacent, 'Aria received the golden crown.', None]:
            with self.subTest(evidence=evidence), \
                 patch.object(ai.requests, 'post', return_value=self.response([
                     self.row(0, evidence, category='item'),
                 ])):
                result = ai.analyze_timeline_events([(text, '')],
                    contexts=[(adjacent, text, adjacent)])[0]
            self.assertFalse(result.keep)
            self.assertIsNone(self.generator._create_event_from_group(
                [TimelineGroupingTests.segment(text)], ai_analysis=result))

    def test_contextual_item_classification_cannot_bypass_action_evidence(self):
        for text in [
            'The silver key lies on the table.',
            'Aria did not receive the silver key.',
            'If Aria took the key, the door would open.',
            'I am going to take the silver key.',
            'I take the attack action.',
            'I use three dice for the damage roll.',
            'I use my proficiency bonus.',
        ]:
            with self.subTest(text=text), \
                 patch.object(ai.requests, 'post', return_value=self.response([
                     self.row(0, text, category='item'),
                 ])) as post:
                events, _ = self.generate([text])
                self.assertEqual(events, [])
                post.assert_called_once()

    def test_occurrence_and_importance_still_gate_contextual_classification(self):
        for text, overrides in [
            ('We might attack the goblin tomorrow.', dict(occurred=False, category='combat')),
            ('Do I need to roll for initiative?', dict(keep=False, category='combat')),
            ('We discuss how attack bonuses work.', dict(importance=0.2, category='combat')),
        ]:
            with self.subTest(text=text), patch.object(ai.requests, 'post',
                    return_value=self.response([self.row(0, text, **overrides)])):
                events, _ = self.generate([text])
                self.assertEqual(events, [])

    def test_completed_event_with_unrelated_negation_survives(self):
        text = 'The goblin could not escape, and the party killed him.'
        with patch.object(ai.requests, 'post', return_value=self.response([
            self.row(0, text, category='combat'),
        ])):
            events, _ = self.generate([text])
        self.assertEqual(events[0].title, text)
        self.assertEqual(events[0].category, TimelineCategory.combat)

    def test_offline_context_fragment_is_not_promoted_to_unvalidated_event(self):
        with patch.object(ai.requests, 'post', side_effect=ai.requests.Timeout()) as post:
            events, count = self.generate(['I open it.'] * 25)
        self.assertEqual(count, 25)
        self.assertEqual(events, [])
        post.assert_called_once()

    def test_disabled_ai_uses_conservative_filter_without_requests(self):
        with patch.object(ai, 'TIMELINE_AI_ENABLED', False), \
             patch.object(self.generator, '_detect_category', return_value=TimelineCategory.item), \
             patch.object(self.generator, '_extract_event_entities', return_value=([], [])), \
             patch.object(ai.requests, 'post') as post:
            events, _ = self.generate(['I open it.', 'The guard mentioned the silver key.',
                                       'Aria received the silver key.'])
        self.assertEqual([event.title for event in events], ['Aria received the silver key.'])
        post.assert_not_called()

    def test_ooc_and_obvious_noise_never_reach_llm(self):
        with patch.object(ai.requests, 'post') as post:
            events, _ = self.generate(['Our sponsor gave us the silver key.'])
        self.assertEqual(events, [])
        post.assert_not_called()
        with patch.object(self.generator, 'semantic_event_decision',
                return_value=types.SimpleNamespace(keep=False, non_event_score=0.9, margin=-0.4)), \
             patch.object(ai.requests, 'post') as post:
            events, _ = self.generate(['We are talking about snacks and scheduling.'])
        self.assertEqual(events, [])
        post.assert_not_called()

    def test_chronological_context_edges_and_missing_response_ids_stay_aligned(self):
        texts = ['We discovered the hidden passage.', 'Aria received the silver key.',
                 'The party arrived in Waterdeep.']
        with patch.object(ai.requests, 'post', return_value=self.response([
            self.row(2, texts[2], category='travel'),
            self.row(0, texts[0]), self.row(0, texts[0]),
        ])) as post, \
             patch.object(self.generator, '_is_meaningful_group', side_effect=
                          lambda group, context_aware=False: context_aware):
            events, _ = self.generate(texts)
        self.assertEqual([event.title for event in events], [texts[2]])
        items = json.loads(post.call_args.kwargs['json']['messages'][1]['content'])
        self.assertEqual([(item['previous'], item['following']) for item in items],
                         [('', texts[1]), (texts[0], texts[2]), (texts[1], '')])

    def test_context_is_bounded_and_current_transcript_is_not_truncated(self):
        text = 'Aria received the silver key. ' + 'The guard waved. ' * 100
        previous = 'P' * 2000 + ' nearby chest'
        following = 'Inside is a sword. ' + 'F' * 2000
        with patch.object(ai.requests, 'post', return_value=self.response([
            self.row(0, 'Aria received the silver key.', category='item'),
        ])) as post:
            result = ai.analyze_timeline_events([(text, '')],
                contexts=[(previous, 'ignored mismatched current', following)])[0]
        self.assertTrue(result.keep)
        items = json.loads(post.call_args.kwargs['json']['messages'][1]['content'])
        self.assertEqual(items[0]['transcript'], text.strip())
        self.assertEqual(items[0]['previous'], previous[-ai.TIMELINE_AI_CONTEXT_CHARS:])
        self.assertEqual(items[0]['following'], following[:ai.TIMELINE_AI_CONTEXT_CHARS])

    def test_context_counts_toward_batch_size_limit(self):
        text = 'Aria received the silver key. ' + 'X' * 4800
        context = ('P' * 1000, text, 'F' * 1000)
        with patch.object(ai.requests, 'post', return_value=self.response([])) as post:
            ai.analyze_timeline_events([(text, '')] * 2, contexts=[context] * 2)
        self.assertEqual(post.call_count, 2)
        for call in post.call_args_list:
            self.assertLessEqual(len(call.kwargs['json']['messages'][1]['content']),
                                 ai.TIMELINE_AI_BATCH_CHARS)

    def test_mismatched_context_count_fails_before_request(self):
        with patch.object(ai.requests, 'post') as post, self.assertRaises(ValueError):
            ai.analyze_timeline_events([('I open it.', '')], contexts=[])
        post.assert_not_called()


if __name__ == '__main__':
    unittest.main()

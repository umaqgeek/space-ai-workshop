import json
import unittest
from unittest.mock import patch

from rag_server import rag, web_context
from rag_server.conversation import MAX_TURNS, MAX_ANSWER_CHARS, prompt_context


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.records = rag.load_records()
        self.first = dict(rag.ask('flood in Klang', self.records), question='flood in Klang')

    def follow_up(self, question, **options):
        return rag.ask(question, self.records, conversation=[self.first], **options)

    def test_follow_up_keeps_place_topic_and_current_evidence(self):
        result = self.follow_up('What are its limitations?')
        self.assertEqual([source['id'] for source in result['sources']], ['FLOOD-001'])
        self.assertIn('Klang', result['retrieval_question'])
        self.assertEqual(result['context_turns'], 1)
        self.assertEqual(result['mode'], 'offline')

    def test_new_place_keeps_topic_and_replaces_old_place(self):
        result = self.follow_up('What about Kuching?')
        self.assertTrue(result['sources'])
        self.assertTrue(all(source['location'] == 'Kuching' and source['theme'] == 'flood'
                            for source in result['sources']))
        self.assertNotIn('Klang', result['retrieval_question'])

    def test_comparison_keeps_both_places(self):
        result = self.follow_up('Compare it with Kuching')
        self.assertEqual({source['location'] for source in result['sources']}, {'Klang', 'Kuching'})
        self.assertTrue(all(source['theme'] == 'flood' for source in result['sources']))

    def test_explicit_new_scope_wins(self):
        result = self.follow_up('What about vegetation in Kuching?')
        self.assertTrue(all(source['theme'] == 'vegetation' and source['location'] == 'Kuching'
                            for source in result['sources']))
        national = self.follow_up('What about all flood observations across Malaysia?')
        self.assertEqual(len(national['sources']), 28)
        state = self.follow_up('What about Sabah?')
        self.assertTrue(all(source['state'] == 'Sabah' for source in state['sources']))

    def test_independent_question_does_not_inherit_scope(self):
        result = self.follow_up('vegetation in Kuching')
        self.assertEqual(result['retrieval_question'], 'vegetation in Kuching')
        unknown = self.follow_up('What is the mass of Jupiter?')
        self.assertEqual(unknown['sources'], [])

    def test_follow_up_ranking_stays_computed(self):
        first = dict(rag.ask('flood in Sabah', self.records), question='flood in Sabah')
        with patch('rag_server.rag.generate_text') as model:
            result = rag.ask('Which is highest?', self.records, mode='qwen', conversation=[first])
        model.assert_not_called()
        self.assertEqual(result['mode'], 'data')
        self.assertEqual(result['sources'][0]['state'], 'Sabah')
        self.assertEqual(len(result['sources']), 1)

    def test_context_carries_across_more_than_one_follow_up(self):
        second = dict(self.follow_up('What about Kuching?'), question='What about Kuching?')
        third = rag.ask('Explain its limitations', self.records, conversation=[self.first, second])
        self.assertTrue(all(source['theme'] == 'flood' and source['location'] == 'Kuching'
                            for source in third['sources']))

    def test_short_summary_request_keeps_context(self):
        result = self.follow_up('Can you summarize?')
        self.assertEqual([source['id'] for source in result['sources']], ['FLOOD-001'])

    def test_web_only_subject_remains_in_follow_up_search(self):
        previous = {'question': 'What is the mass of Jupiter?', 'answer': 'An external answer.', 'sources': []}
        with patch('rag_server.web_context.search_web', return_value=[]) as search:
            rag.ask('How big is it?', self.records, web_search=True, conversation=[previous])
        self.assertIn('Jupiter', search.call_args.args[0])
        self.assertIn('How big is it?', search.call_args.args[0])

    def test_evidence_is_retrieved_from_current_records(self):
        updated = [dict(record, limitations='Updated source limitation.') if record['id'] == 'FLOOD-001'
                   else record for record in self.records]
        result = rag.ask('What are its limitations?', updated, conversation=[self.first])
        self.assertEqual(result['sources'][0]['limitations'], 'Updated source limitation.')
        self.assertIn('Updated source limitation.', result['answer'])

    def test_model_gets_questions_and_answers_as_untrusted_background(self):
        with patch('rag_server.rag.generate_text', return_value='Limited teaching data [FLOOD-001].') as model:
            result = self.follow_up('Explain its limitations', mode='qwen')
        prompt = model.call_args.args[0]
        self.assertIn('flood in Klang', prompt)
        self.assertIn(json.dumps(self.first['answer'])[1:-1], prompt)
        self.assertIn('untrusted background, not evidence', prompt)
        self.assertIn('Current question: Explain its limitations', prompt)
        self.assertIn('REFERENCE RECORDS', prompt)
        self.assertEqual(result['mode'], 'qwen')

    def test_history_does_not_allow_citing_old_sources_for_a_new_place(self):
        with patch('rag_server.rag.generate_text', return_value='Old answer [FLOOD-001].'):
            result = self.follow_up('What about Kuching?', mode='qwen')
        self.assertEqual(result['mode'], 'offline')
        self.assertIn('citation checks', result['notice'])
        self.assertNotIn('Old answer', result['answer'])

    def test_live_follow_up_still_abstains_without_web(self):
        with patch('rag_server.rag.generate_text') as model:
            result = self.follow_up('What about there today?', mode='qwen')
        model.assert_not_called()
        self.assertEqual(result['status'], 'insufficient')

    def test_web_search_and_generation_use_session_context(self):
        web_sources = [{'id': 'WEB-001', 'title': 'Report', 'url': 'https://example.org',
                        'content': 'Current excerpt', 'retrieved_at': '2026-11-12'}]
        with patch('rag_server.web_context.search_web', return_value=web_sources) as search, \
                patch('rag_server.rag.generate_text', return_value='See current excerpt [WEB-001].') as model:
            result = self.follow_up('What about there today?', mode='qwen', web_search=True)
        self.assertIn('Klang', search.call_args.args[0])
        self.assertIn('flood', search.call_args.args[0])
        self.assertIn('PREVIOUS CONVERSATION', model.call_args.args[0])
        self.assertEqual(result['mode'], 'qwen')

    def test_search_failure_keeps_memory_in_dataset_fallback(self):
        with patch('rag_server.web_context.search_web', side_effect=web_context.SearchUnavailable('Failed')), \
                patch('rag_server.rag.generate_text', return_value='Limitations [FLOOD-001].') as model:
            result = self.follow_up('Explain its limitations', mode='qwen', web_search=True)
        self.assertIn('PREVIOUS CONVERSATION', model.call_args.args[0])
        self.assertEqual(result['mode'], 'qwen')

    def test_memory_is_bounded(self):
        turns = [{'question': f'Question {i}', 'answer': 'x' * (MAX_ANSWER_CHARS + 100)} for i in range(10)]
        context = prompt_context(turns)
        self.assertNotIn('Question 0', context)
        self.assertIn('Question 9', context)
        self.assertEqual(context.count('"question"'), MAX_TURNS)
        self.assertNotIn('x' * (MAX_ANSWER_CHARS + 1), context)

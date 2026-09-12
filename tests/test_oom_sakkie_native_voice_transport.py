"""Execute proposed n8n Code-node bodies locally; never execute a cloud workflow."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / 'docs/04-n8n/workflows'
PATCH = WORKFLOWS / '2 - The GateKeeper/NATIVE_VOICE_TRANSPORT_PATCH_20260912.json'
GATE = 'Code - Gate BEACON Single Photo'
SWITCH = 'Switch - BEACON Media Intake'
RELAY = 'Code - Normalize GateKeeper Message'
HTTP = 'Relay Owner Request Media to Gateway'
OWNER, DAD = 9910001, 9910002


def packet():
    return json.loads(PATCH.read_text(encoding='utf-8'))


def edit(name, field='parameters.jsCode'):
    return next(item for item in packet()['edits'] if item['node_name'] == name and item['field'] == field)


def run_js(code, payload, variables=None):
    harness = '''const vm = require('node:vm');
const data = JSON.parse(process.argv[1]);
const result = new vm.Script('(function () {"use strict";\\n' + data.code + '\\n})()')
  .runInNewContext({$json: data.payload, $vars: data.variables}, {timeout: 200});
process.stdout.write(JSON.stringify(result[0].json));'''
    result = subprocess.run(['node', '-e', harness, json.dumps({'code': code, 'payload': payload,
        'variables': variables or {}})], capture_output=True, text=True, check=True, timeout=5)
    return json.loads(result.stdout)


def update(user=DAD, **message_changes):
    message = {'message_id': 903, 'date': 1789234800, 'from': {'id': user, 'is_bot': False},
        'chat': {'id': user, 'type': 'private'},
        'voice': {'file_id': 'SYNTHETIC_NATIVE_VOICE', 'file_unique_id': 'SYNTHETIC_UNIQUE',
                  'duration': 1, 'file_size': 100, 'mime_type': 'audio/ogg'},
        'reply_to_message': {'message_id': 900, 'text': 'SYNTHETIC PRIOR QUESTION'}}
    message.update(message_changes)
    raw = {'update_id': 904, 'message': message}
    return {'raw_update': raw, 'user_id': str(user), 'chat_id': str(user),
            'message_id': str(message['message_id']), 'message_text': message.get('text', ''),
            'is_authorized': True}


class NativeVoiceTransportTests(unittest.TestCase):
    def gate(self, value, phase='after'):
        return run_js(edit(GATE)[phase], value,
            {'BEACON_MEDIA_INTAKE_OWNER_USER_ID': str(OWNER), 'BEACON_MEDIA_INTAKE_PRIVATE_CHAT_ID': str(OWNER)})

    def targets(self, route, phase='after'):
        rules = edit(SWITCH, 'parameters.rules.values')[phase]
        index = next(index for index, item in enumerate(rules)
                     if item['conditions']['conditions'][0]['rightValue'] == route)
        return edit(SWITCH, 'connections.main')[phase][index]

    def test_published_voice_rejection_becomes_one_raw_backend_handoff(self):
        for user in (OWNER, DAD):
            with self.subTest(user=user):
                value = update(user)
                before = self.gate(value, 'before')
                self.assertEqual(before['gatekeeper_media_route'], 'media_rejected')
                self.assertEqual(self.targets('media_rejected', 'before'), [])
                after = self.gate(value)
                self.assertEqual(after['gatekeeper_media_route'], 'family_native_voice')
                self.assertEqual(self.targets('family_native_voice'), [{'node': HTTP, 'type': 'main', 'index': 0}])
                self.assertEqual(after['raw_update'], value['raw_update'])
                self.assertEqual(packet()['unchanged_transport']['jsonBody'], '={{ $json.raw_update }}')

    def test_private_chat_and_flat_identity_conflicts_do_not_reach_voice_transport(self):
        cases = [update(chat={'id': DAD, 'type': 'group'}), update(chat={'id': OWNER, 'type': 'private'}),
                 {**update(), 'user_id': str(OWNER)}, {**update(), 'chat_id': str(OWNER)}]
        for value in cases:
            with self.subTest(value=value):
                result = self.gate(value)
                self.assertEqual(result['gatekeeper_media_route'], 'media_rejected')
                self.assertEqual(self.targets(result['gatekeeper_media_route']), [])

    def test_mixed_attachments_stay_rejected(self):
        cases = [{'audio': {'file_id': 'SYNTHETIC_AUDIO'}}, {'document': {'file_id': 'SYNTHETIC_DOC'}},
                 {'photo': [{'file_id': 'SYNTHETIC_PHOTO', 'file_unique_id': 'SYNTHETIC_PHOTO'}]},
                 {'media_group_id': 'SYNTHETIC_GROUP'}, {'voice': 'MALFORMED'}, {'voice': []}]
        for changes in cases:
            with self.subTest(changes=changes):
                result = self.gate(update(**changes))
                self.assertEqual(result['gatekeeper_media_route'], 'media_rejected')

    def test_report_provenance_is_preserved_for_backend_rejection(self):
        value = update(forward_origin={'type': 'hidden_user', 'sender_user_name': 'SYNTHETIC'})
        result = self.gate(value)
        self.assertEqual(result['gatekeeper_media_route'], 'family_native_voice')
        self.assertEqual(result['raw_update'], value['raw_update'])
        # The transport does not remove provenance or claim transcription/authority.
        self.assertNotIn('input_provenance', result)
        self.assertNotIn('transcript', result)

    def test_existing_photo_album_text_and_callback_outputs_are_unchanged(self):
        photo = update(OWNER, voice=None, photo=[{'file_id': 'SYNTHETIC_PHOTO', 'file_unique_id': 'SYNTHETIC_PHOTO'}])
        album = copy.deepcopy(photo)
        album['raw_update']['message']['media_group_id'] = 'SYNTHETIC_ALBUM'
        typed = update(OWNER, voice=None, text='How are things?')
        callback = {'raw_update': {'callback_query': {'id': 'SYNTHETIC_CALLBACK', 'data': 'oompa:SYNTHETIC:confirm'}},
                    'user_id': str(OWNER), 'chat_id': str(OWNER)}
        for value in (photo, album, typed, callback):
            with self.subTest(value=value):
                self.assertEqual(self.gate(value)['gatekeeper_media_route'],
                                 self.gate(value, 'before')['gatekeeper_media_route'])
        self.assertEqual(edit(SWITCH, 'parameters.rules.values')['after'][:4],
                         edit(SWITCH, 'parameters.rules.values')['before'])
        self.assertEqual(edit(SWITCH, 'connections.main')['after'][:4], edit(SWITCH, 'connections.main')['before'])

    def test_typed_reply_preserves_only_the_native_card_id(self):
        value = update(voice=None, text='Gister, en die liggaam is verwyder.')
        before = run_js(edit(RELAY)['before'], value)
        self.assertTrue(before['success'])
        self.assertNotIn('reply_to_message', before['gateway_payload']['message'])
        after = run_js(edit(RELAY)['after'], value)
        self.assertTrue(after['success'])
        self.assertEqual(after['gateway_payload']['message']['reply_to_message'], {'message_id': 900})
        without_reply = copy.deepcopy(after)
        del without_reply['gateway_payload']['message']['reply_to_message']
        self.assertEqual(without_reply, before)

    def test_typed_reply_with_invalid_native_card_id_fails_closed(self):
        for reply in ({}, None, '900', [], {'message_id': '900'}, {'message_id': True},
                      {'message_id': 0}, {'message_id': -1}, {'message_id': 2 ** 54}):
            value = update(voice=None, text='Ja.', reply_to_message=reply)
            with self.subTest(reply=reply):
                result = run_js(edit(RELAY)['after'], value)
                self.assertEqual(result['status'], 'invalid_relay_input')
                self.assertFalse(result['send_allowed'])
                self.assertNotIn('gateway_payload', result)

    def test_absent_reply_and_flat_substitution_retain_existing_contract(self):
        value = update(voice=None, text='Die water is nog laag.')
        del value['raw_update']['message']['reply_to_message']
        self.assertEqual(run_js(edit(RELAY)['after'], value), run_js(edit(RELAY)['before'], value))
        for key in ('user_id', 'chat_id', 'message_id', 'message_text'):
            altered = {**value, key: 'SYNTHETIC_CONFLICT'}
            with self.subTest(key=key):
                result = run_js(edit(RELAY)['after'], altered)
                self.assertFalse(result['success'])
                self.assertNotIn('gateway_payload', result)

    def test_patch_is_exact_reversible_data_and_keeps_legacy_exports_unchanged(self):
        data = packet()
        self.assertEqual(len(data['edits']), 4)
        self.assertEqual({item['workflow_id'] for item in data['edits']}, {'s8QaxmqT69Z5mhvE', 'TlKy9kUgJJE0msU4'})
        for item in data['edits']:
            for phase in ('before', 'after'):
                encoded = json.dumps(item[phase], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), item[phase + '_sha256'])
            if item['field'] == 'parameters.jsCode':
                repo = json.loads((WORKFLOWS / item['workflow_name'] / 'workflow.json').read_text(encoding='utf-8-sig'))
                original = next(node for node in repo['nodes'] if node['name'] == item['node_name'])
                self.assertEqual(original['parameters']['jsCode'], item['before'])
        self.assertEqual(data['effects'], {'production_changes': 0, 'n8n_executions': 0, 'messages_sent': 0, 'audio_calls': 0})
        self.assertFalse(data['unchanged_transport']['retryOnFail'])
        self.assertFalse(data['unchanged_transport']['secret_or_variable_values_in_packet'])


if __name__ == '__main__':
    unittest.main()

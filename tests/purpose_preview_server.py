"""Local synthetic preview: actual template/assets and canonical read-only producer.

No app import, real database, owner session or write endpoint. Browser tests
intercept simulated create/approve/execute; this server refuses those routes.
"""
import os
from datetime import date
from pathlib import Path

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['OWNER_SESSION_SECRET'] = 'synthetic-purpose-preview-only-not-an-owner-credential'
for key in list(os.environ):
    if 'DATABASE_URL' in key or key.endswith('POSTGRES_URL'):
        os.environ.pop(key)

from flask import Flask, jsonify, render_template, request
from modules.pig_weights.purpose_correction_batch_service import preview_correction_batch

ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, template_folder=str(ROOT / 'templates'), static_folder=str(ROOT / 'static'))
ROWS = [{
    'pig_id': f'SYNTHETIC-PURPOSE-{i}', 'tag_number': str(140 + i),
    'purpose': 'Unknown', 'status': 'Active', 'on_farm': True,
    'animal_type': 'Weaner', 'sex': 'Female', 'current_pen_name': 'Test pen',
    'readiness_bucket': 'Needs Classification', 'suggested_purpose': 'Grow Out',
    'suggested_purpose_reason': 'Qualifying post-wean weight is recorded; owner purpose decision required.',
    'latest_weight_date': '2026-09-30', 'latest_weight_kg': 18.5 + i,
    'litter_id': 'SYNTHETIC-LITTER', 'days_since_weight': 4,
} for i in (1, 2)]

class ReadOnlyFixture:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, params=None):
        assert query.strip().lower() == 'set transaction isolation level repeatable read read only' or (
            query.lstrip().lower().startswith('select pig.pig_id,') and 'public.current_canonical_pigs' in query)
        if params: self.ids = params[0]
    def cursor(self): return self
    def fetchall(self):
        return [(r['pig_id'], r['tag_number'], r['status'], r['on_farm'], r['purpose'],
                 date.fromisoformat(r['latest_weight_date']), r['latest_weight_kg'])
                for r in ROWS if r['pig_id'] in self.ids]

@app.get('/pig-allocation')
def page():
    banner = ('<aside role="note" style="padding:12px;text-align:center;background:#fff0c4;color:#302800">'
              'Local test preview &mdash; synthetic animals; saving farm records is disabled.</aside>')
    return render_template('pig-allocation.html').replace('<body>', '<body>' + banner, 1)

@app.get('/api/pig-weights/pig-allocation-readiness')
def allocation():
    return jsonify(success=True, pigs=ROWS, summary={'total': 2, 'buckets': {'Needs Classification': 2}},
                   business_rules={}, generated_date='2026-10-04')

@app.post('/api/pig-weights/purpose-review/apply')
def preview():
    payload = request.get_json() or {}
    body, status = preview_correction_batch(payload.get('decisions'), actor_id='synthetic-owner',
        return_to=payload.get('return_to', ''), connect_factory=lambda _: ReadOnlyFixture())
    return jsonify(body), status

@app.route('/api/pig-weights/<path:unused>', methods=['GET', 'POST'])
def unavailable(unused):
    return jsonify(success=False, status='synthetic_preview_no_write_routes'), 405

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PURPOSE_PREVIEW_PORT', '5219')), debug=False, use_reloader=False)

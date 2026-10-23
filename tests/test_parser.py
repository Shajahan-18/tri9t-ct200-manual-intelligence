from app.parser import parse_pdf, sha
from pathlib import Path
DATA=Path(__file__).resolve().parents[1]/'data'

def test_v1_and_v2_parse_and_keep_changed_body():
    v1=parse_pdf(DATA/'ct200_manual_v1.pdf',1)
    v2=parse_pdf(DATA/'ct200_manual_v2.pdf',2)
    assert v1['nodes'] and v2['nodes']
    b1=next(n for n in v1['nodes'] if 'Battery Life Under Typical Use' in n['heading'])
    b2=next(n for n in v2['nodes'] if 'Battery Life Under Typical Use' in n['heading'])
    assert '300 measurement cycles' in b1['body']
    assert '250 measurement cycles' in b2['body']
    assert b1['content_hash'] != b2['content_hash']

def test_irregular_missing_intermediate_heading_is_not_fabricated():
    parsed=parse_pdf(DATA/'ct200_manual_v2.pdf',2)
    battery=next(n for n in parsed['nodes'] if 'Battery Life Under Typical Use' in n['heading'])
    assert battery['number']=='2.1.1.1'
    assert battery['level']==4
    # No invented 2.1.1 node: the parser preserves the real parent it can infer.
    assert not any(n['number']=='2.1.1' for n in parsed['nodes'])

def test_out_of_order_3_4_then_3_3_are_both_preserved():
    parsed=parse_pdf(DATA/'ct200_manual_v1.pdf',1)
    nums=[n['number'] for n in parsed['nodes']]
    assert '3.4' in nums and '3.3' in nums
    assert nums.index('3.4') < nums.index('3.3')

def test_hash_is_deterministic():
    assert sha('battery 250') == sha('battery 250')
    assert sha('battery 250') != sha('battery 300')

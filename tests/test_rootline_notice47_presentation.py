from copy import deepcopy
import pytest
from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan, compose_daily_rootline_manager_item, _daily_date
from modules.telemetry.rootline_input_health import CONTRACT
from tests.test_rootline_notice46_presentation import plan

GENERIC = 'Current irrigation need and dry observed weather support the scheduled irrigation run.'

@pytest.mark.parametrize('day,suffix', [(1,'ˢᵗ'),(2,'ⁿᵈ'),(3,'ʳᵈ'),(4,'ᵗʰ'),(11,'ᵗʰ'),(12,'ᵗʰ'),(13,'ᵗʰ'),(21,'ˢᵗ'),(22,'ⁿᵈ'),(23,'ʳᵈ'),(31,'ˢᵗ')])
def test_real_date_ordinal(day,suffix):
    assert f' {day}{suffix}, Jan 2026' in _daily_date(f'2026-01-{day:02}')
    assert '<sup>' not in _daily_date(f'2026-01-{day:02}')

@pytest.mark.parametrize('language,heading,date_text', [('en',"Today's plan",'Thu 26ᵗʰ, Nov 2026'),('af','Vandag se plan','Do 26ˢᵗᵉ, Nov 2026')])
def test_clean_daily_plan_retains_windows_link_and_action(language,heading,date_text):
    value=plan()
    for row in value['recommendations']: row['reason']=GENERIC
    value['owner_brief']={'family_fact_needed':'Please confirm the damaged valve.','reassess':'2026-11-26T15:00:00+02:00'}
    text=compose_daily_rootline_plan(value,language=language)
    assert text.startswith(f'<b>🌿 ROOTLINE · {heading}</b>\n{date_text}\n')
    assert '10h00–11h00' in text and '13h00–14h00' in text
    assert 'SAST' not in text and GENERIC not in text
    assert 'No action needed' not in text and 'Geen aksie nodig' not in text
    assert 'Please confirm the damaged valve.' in text
    assert '/irrigation' in text

@pytest.mark.parametrize('language',['en','af'])
def test_actual_hold_reason_not_hidden_by_generic_reason(language):
    value=plan(); value['recommendations'][0]['reason']=GENERIC
    value['recommendations'][1]['reason']='Fresh local evidence records rain; irrigation waits.'
    text=compose_daily_rootline_plan(value,language=language)
    assert ('reën' if language=='af' else 'rain') in text
    assert GENERIC not in text

@pytest.mark.parametrize('language',['en','af'])
@pytest.mark.parametrize('provider,name,url',[('open_meteo','Open-Meteo','https://open-meteo.com/'),('weatherapi','WeatherAPI.com','https://www.weatherapi.com/'),('visual_crossing','Visual Crossing Weather','https://www.visualcrossing.com/weather-data/')])
def test_provider_credit_once_in_existing_weather_paragraph(language,provider,name,url):
    value=plan();value['forecast']={'source':{'provider':provider}}
    value['input_health']={'contract':CONTRACT,'inputs':{'forecast':{'state':'available_fallback','operating_date':'2026-11-26'}}}
    text=compose_daily_rootline_plan(value,language=language)
    credit=f'<a href="{url}">{name}</a>'
    assert text.count(credit)==1
    line=next(line for line in text.splitlines() if credit in line)
    assert ('rugsteun' if language=='af' else 'backup') in line
    assert ('Weervoorspelling deur' if language=='af' else 'Forecast by') not in line
    assert text.index(credit)<text.index('<b>A ')
    assert text.rstrip().endswith('</a>') and '/irrigation' in text.splitlines()[-1]

@pytest.mark.parametrize('forecast',[None,{}, {'source':{'provider':'unregistered'}}])
def test_no_invented_forecast_credit(forecast):
    value=plan();value['forecast']=forecast
    text=compose_daily_rootline_plan(value)
    assert 'Forecast by' not in text and 'open-meteo.com' not in text

@pytest.mark.parametrize('bad',['','not-a-date','2026-02-30'])
def test_invalid_date_not_invented(bad):
    assert _daily_date(bad)==''

def test_shared_brief_reason_and_credit_contract_unchanged():
    value=plan();value['recommendations'][0]['reason']=GENERIC
    value['forecast']={'source':{'provider':'open_meteo'}}
    brief=compose_daily_rootline_manager_item(value)
    assert GENERIC in brief['why'] and 'Forecast by Open-Meteo.' in brief['why']
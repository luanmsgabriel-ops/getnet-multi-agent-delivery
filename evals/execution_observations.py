"""Bounded process observations from actual public-information transport records."""
import json
from datetime import datetime
from app.public_information import ENDPOINTS

URN = 'urn:getnet:execution:public_information'

def execution_references(network, turn):
    """No answer, expected result or model observations are accepted as inputs."""
    refs = []
    actual = [n for n in network if n.get('turn') == turn and 'data' in n and not n.get('error_type')]
    for n in actual:
        endpoint = n.get('endpoint')
        if endpoint not in (ENDPOINTS['weather'], ENDPOINTS['fx']):
            continue
        try:
            start = datetime.fromisoformat(n['at'])
            end = datetime.fromisoformat(n['completed_at'])
            if start.tzinfo is None or end.tzinfo is None or end < start:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        # Only known nonsensitive fields. No headers, query strings, IDs or answer text.
        info = {'endpoint': endpoint, 'request_started': start.isoformat(timespec='seconds'),
                'request_completed': end.isoformat(timespec='seconds')}
        try:
            received = datetime.fromisoformat(n.get('response_received_at', ''))
            if received.tzinfo is not None and received >= end:
                info['response_received_at'] = received.isoformat()
        except (TypeError, ValueError):
            pass
        if endpoint == ENDPOINTS['weather']:
            params = n.get('params', {})
            dates = {}
            for key in ('start_date', 'end_date'):
                value = params.get(key)
                try:
                    from datetime import date
                    if date.fromisoformat(value).isoformat() == value:
                        dates[key] = value
                except (TypeError, ValueError):
                    pass
            info.update(dates)
            if params.get('timezone') == 'America/Sao_Paulo':
                info['requested_timezone'] = params['timezone']
            if any(x.get('endpoint') == ENDPOINTS['geo'] and x.get('params', {}).get('countryCode') == 'BR' for x in actual):
                info['observed_geocoding_country_filter'] = 'BR'
        refs.append({'kind': 'execution_observation', 'source': URN,
                     'evidence_id': 'execution_' + str(len(refs) + 1),
                     'text': json.dumps(info, ensure_ascii=False)})
    return refs

import requests
import yaml
import argparse
import csv
import urllib.parse
from datetime import datetime, date, time


def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def get_access_token(config):
    url = f"{config['prod_server']}/services/oauth2/token"
    params = {
        'grant_type': 'password',
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'username': config['username'],
        'password': config['password']
    }
    response = requests.post(url, data=params)
    response.raise_for_status()
    return response.json()['access_token']


def build_query(badge_names):
    escaped_badges = [f"'{badge}'" for badge in badge_names]
    joined = ','.join(escaped_badges)
    subquery = f"SELECT OrderApi__Contact__c FROM OrderApi__Badge__c WHERE OrderApi__Badge_Type__r.Name IN ({joined})"
    inner = (
        "SELECT Id, FirstName, LastName, Email, "
        "(SELECT OrderApi__Badge_Type__r.Name, OrderApi__Is_Active__c, OrderApi__Awarded_Date__c, OrderApi__Expired_Date__c "
        "FROM OrderApi__Badges__r) "
        f"FROM Contact WHERE Id IN ({subquery})"
    )
    return urllib.parse.quote(inner, safe='')


def fetch_contacts(config, access_token):
    query = build_query(config['co-chair_badges'])
    url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={query}"
    headers = {"Authorization": f"Bearer {access_token}"}
    all_records = []

    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()
        all_records.extend(result.get('records', []))
        url = result.get('nextRecordsUrl')
        if url:
            url = f"{config['prod_server']}{url}"

    return all_records


def is_badge_active_in_period(badge, start_date, end_date):
    awarded = badge.get('OrderApi__Awarded_Date__c')
    expired = badge.get('OrderApi__Expired_Date__c')
    if not awarded:
        return False

    awarded_dt = datetime.strptime(awarded, "%Y-%m-%d")
    expired_dt = datetime.strptime(expired, "%Y-%m-%d") if expired else None

    if expired_dt and expired_dt < start_date:
        return False
    return awarded_dt <= end_date


def filter_contacts(records, inclusion_badges, exclusion_badges, start_date, end_date, exclude_contact_ids, include_contact_ids, accelerator_badges):
    filtered = []
    accelerator_only = []
    contact_map = {r['Id']: r for r in records}
    included_ids = set()

    for contact in records:
        contact_id = contact.get('Id')
        badges = contact.get('OrderApi__Badges__r', {}).get('records', [])
        active_badges = [
            b for b in badges
            if b.get('OrderApi__Badge_Type__r')
            and is_badge_active_in_period(b, start_date, end_date)
        ]
        active_badge_names = set(b['OrderApi__Badge_Type__r']['Name'] for b in active_badges)

        contact['__active_badge_names'] = active_badge_names
        contact['__matching_badge_names'] = active_badge_names.intersection(inclusion_badges)

        if contact_id in include_contact_ids:
            included_ids.add(contact_id)
            filtered.append(contact)
            continue

        if contact_id in exclude_contact_ids:
            name = f"{contact.get('FirstName', '')} {contact.get('LastName', '')}".strip()
            print(f"Excluded by ID: {name} ({contact_id})")
            continue

        if active_badge_names.intersection(exclusion_badges):
            name = f"{contact.get('FirstName', '')} {contact.get('LastName', '')}".strip()
            print(f"Excluded by badge: {name} ({'; '.join(active_badge_names)})")
            continue

        matching_badges = active_badge_names.intersection(inclusion_badges)

        if 'HL7 Co-Chair' in matching_badges \
           and len(matching_badges) == 1 \
           and active_badge_names.intersection(accelerator_badges):
            accelerator_only.append(contact)
        elif matching_badges:
            filtered.append(contact)

    return filtered, accelerator_only


def write_csv(records, filepath):
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Id', 'Name', 'Email', 'Badges', 'Active in Period'])
        for contact in records:
            contact_id = contact.get('Id', '')
            name = f"{contact.get('FirstName', '')} {contact.get('LastName', '')}".strip()
            email = contact.get('Email', '')
            badges = contact.get('OrderApi__Badges__r', {}).get('records', [])
            badge_display = sorted(set(
                f"{b['OrderApi__Badge_Type__r']['Name']} ({'Active' if b.get('OrderApi__Is_Active__c') else 'Inactive'})"
                for b in badges if b.get('OrderApi__Badge_Type__r')
            ))
            active_in_period = sorted(contact.get('__matching_badge_names', []))
            writer.writerow([contact_id, name, email, '; '.join(badge_display), '; '.join(active_in_period)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True, help='Path to YAML config file')
    parser.add_argument('-o', '--output', help='Path to output CSV for main list')
    parser.add_argument('-ao', '--accelerator-output', help='Optional path to output CSV for HL7 Co-Chair accelerator-only list')
    args = parser.parse_args()

    config = load_config(args.config)
    start_date = datetime.combine(config['start_date'], time.min)
    end_date = datetime.combine(config['end_date'], time.max)
    inclusion_badges = set(config.get('co-chair_badges', []))
    exclusion_badges = set(config.get('co-chair_exclusion_badges', []))
    accelerator_badges = set(config.get('accelerator_badges', []))
    exclude_contact_ids = set(config.get('exclude_contact_ids', []))
    include_contact_ids = set(config.get('include_contact_ids', []))

    token = get_access_token(config)
    records = fetch_contacts(config, token)
    filtered_records, accelerator_only = filter_contacts(
        records,
        inclusion_badges,
        exclusion_badges,
        start_date,
        end_date,
        exclude_contact_ids,
        include_contact_ids,
        accelerator_badges
    )

    print(f"Found {len(filtered_records)} unique contacts with one or more specified badges (after exclusions).")
    if accelerator_only:
        print(f"Found {len(accelerator_only)} HL7 Co-Chairs with only accelerator badges.")

    if args.output:
        write_csv(filtered_records, args.output)
        print(f"Results written to {args.output}")

    if args.accelerator_output:
        write_csv(accelerator_only, args.accelerator_output)
        print(f"Accelerator-only results written to {args.accelerator_output}")


if __name__ == '__main__':
    main()

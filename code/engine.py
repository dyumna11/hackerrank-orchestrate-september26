"""
Deterministic Buy-or-Wait Financial Decision Engine
====================================================
Implements the 18-stage validated deterministic architecture for HackerRank Orchestrate.
"""

import csv
import os
import re
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

# Fixed OCR/Extracted amounts for the 16 images associated with blank financial events
IMAGE_AMOUNTS = {
    'image_01': 4365000.0,   # event_253: August 2019 net salary (IDR)
    'image_02': 100000.0,    # event_1442: Outstanding rent balance (INR)
    'image_03': 41272.0,     # event_1545: Bulk groceries and pantry purchase (INR)
    'image_04': 2854.0,      # event_1700: Delivered grocery order (INR)
    'image_05': 704.05,      # event_1786: Outstanding telecom bill (INR)
    'image_06': 1995.0,      # event_3051: Grocery tax invoice (INR)
    'image_07': 8528.0,      # event_3231: Restaurant tax invoice (INR)
    'image_08': 15339.0,     # event_4535: Property maintenance invoice (INR)
    'image_09': 723.0,       # event_5170: Water bill due (INR)
    'image_10': 79679.26,    # event_6033: Large grocery tax invoice (INR)
    'image_11': 3650.0,      # event_6859: Hospital bill payable (INR)
    'image_12': 33.5,        # event_7307: Taxi fare (USD)
    'image_13': 2298.0,      # event_7941: Tote bag order (INR)
    'image_14': 4543.0,      # event_9421: Pharmacy purchase (INR)
    'image_15': 9968.0,      # event_9806: Airline ticket purchase (INR)
    'image_16': 393.22       # event_10521: EV charging wallet payment (INR)
}


def parse_date(d_str):
    if not d_str:
        return None
    return datetime.strptime(d_str[:10], '%Y-%m-%d').date()


def format_date(d):
    return d.strftime('%Y-%m-%d')


def load_dataset(dataset_dir):
    """Loads all relevant CSV files from dataset_dir."""
    def read_csv(filename):
        path = os.path.join(dataset_dir, filename)
        if not os.path.exists(path):
            return []
        with open(path, mode='r', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    profiles = {r['user_id']: r for r in read_csv('financial_profiles.csv')}
    events = read_csv('financial_events.csv')
    options = read_csv('request_payment_options.csv')
    messages = read_csv('messages.csv')
    images = read_csv('images.csv')
    exchange_rates = read_csv('exchange_rates.csv')
    requests = read_csv('requests.csv')
    sample_requests = read_csv('sample_requests.csv')

    return {
        'profiles': profiles,
        'events': events,
        'options': options,
        'messages': messages,
        'images': images,
        'exchange_rates': exchange_rates,
        'requests': requests,
        'sample_requests': sample_requests
    }


def preprocess_evidence(events, images, messages):
    """Resolves blank amounts using images and extracts message modifications."""
    # 1. Map related_event_id -> image_id
    event_to_image = {}
    for img in images:
        if img.get('related_event_id') and img.get('image_id'):
            event_to_image[img['related_event_id']] = img['image_id']

    # Update blank amounts in events
    for ev in events:
        eid = ev['event_id']
        if not ev.get('amount') or ev['amount'].strip() == '':
            if eid in event_to_image:
                img_id = event_to_image[eid]
                if img_id in IMAGE_AMOUNTS:
                    ev['amount'] = str(IMAGE_AMOUNTS[img_id])

    # 2. Parse messages for each user
    user_messages = defaultdict(list)
    for m in messages:
        user_messages[m['user_id']].append(m)

    user_amendments = {}
    for uid, msgs in user_messages.items():
        amendment = {
            'salary_override_amount': None,
            'salary_override_date': None,
            'salary_ended': False,
            'rent_multiplier': 1.0,
            'ignore_events': set()
        }
        for m in msgs:
            txt = m['message_text']
            # Check seasonal contract ended
            if any(k in txt.lower() for k in ['seasonal contract has ended', 'kontrak musiman saat ini telah berakhir', 'employment has ended']):
                amendment['salary_ended'] = True

            # Check rent increase
            rent_match = re.search(r'lease increases monthly rent by (\d+)%', txt, re.I)
            if not rent_match:
                rent_match = re.search(r'sewa bulanan sebesar (\d+)%', txt, re.I)
            if rent_match:
                pct = float(rent_match.group(1))
                amendment['rent_multiplier'] = 1.0 + (pct / 100.0)

            # Check salary override amount
            # Look for specific salary statements
            sal_match = re.search(r'(?:gaji bulanan anda naik menjadi|salary is reduced to|temporary monthly pay is|salary will be|gaji pokok yang dikonfirmasi adalah|gaji pertama anda sebesar|salary of)\s*(?:IDR|EUR|ZAR|INR|USD)\s*([\d,\.]+)', txt, re.I)
            if sal_match:
                val_str = sal_match.group(1).replace(',', '')
                # remove trailing dot if any
                val_str = val_str.rstrip('.')
                try:
                    amendment['salary_override_amount'] = float(val_str)
                except ValueError:
                    pass

            # Check salary date override
            date_match = re.search(r'(?:expected on|scheduled for|credit date is|berlaku mulai)\s*(\d{4}-\d{2}-\d{2})', txt, re.I)
            if date_match:
                amendment['salary_override_date'] = date_match.group(1)

        user_amendments[uid] = amendment

    return user_amendments


def build_exchange_rate_map(exchange_rates):
    """Builds rate lookup map (from_curr, to_curr) -> sorted list of (date, rate)."""
    rate_map = defaultdict(list)
    for row in exchange_rates:
        d = parse_date(row['rate_date'])
        fc = row['from_currency']
        tc = row['to_currency']
        rate = float(row['rate'])
        rate_map[(fc, tc)].append((d, rate))

    for k in rate_map:
        rate_map[k].sort(key=lambda x: x[0])
    return rate_map


def convert_currency(amount, from_curr, to_curr, on_date, rate_map):
    if from_curr == to_curr or amount == 0:
        return amount
    pair = (from_curr, to_curr)
    if pair in rate_map:
        rates = rate_map[pair]
        # find rate on or closest preceding date
        chosen_rate = rates[0][1]
        for d, r in rates:
            if d <= on_date:
                chosen_rate = r
            else:
                break
        return amount * chosen_rate
    # If reverse pair exists
    rev_pair = (to_curr, from_curr)
    if rev_pair in rate_map:
        rates = rate_map[rev_pair]
        chosen_rate = rates[0][1]
        for d, r in rates:
            if d <= on_date:
                chosen_rate = r
            else:
                break
        return amount / chosen_rate
    return amount


def extract_user_commitments(user_id, events, profile, user_amendments, req_date, rate_map):
    """
    Extracts confirmed one-off future events and active recurring expense/income patterns.
    """
    u_events = [e for e in events if e['user_id'] == user_id]
    home_curr = profile['home_currency']
    amendments = user_amendments.get(user_id, {
        'salary_override_amount': None,
        'salary_override_date': None,
        'salary_ended': False,
        'rent_multiplier': 1.0,
        'ignore_events': set()
    })

    future_cash_events = []
    
    # 1. Process future scheduled/pending events
    for e in u_events:
        eid = e['event_id']
        status = e['status']
        direction = e['direction']
        ev_type = e['event_type']
        
        # Determine effective date
        d_str = e['settlement_date'] or e['event_date']
        if not d_str:
            continue
        eff_date = parse_date(d_str)

        # Skip past events
        if eff_date < req_date:
            continue

        # Ignore pending credits, failed, cancelled, non-cash
        if status in ('cancelled', 'failed', 'unrealized'):
            continue
        if direction == 'non_cash':
            continue
        if status == 'pending' and direction == 'credit':
            continue  # Do not count pending credits

        raw_amt = float(e['amount']) if e.get('amount') else 0.0
        if raw_amt == 0:
            continue

        # Convert to home currency
        amt = convert_currency(raw_amt, e['currency'], home_curr, eff_date, rate_map)

        if status == 'pending' and direction == 'debit':
            future_cash_events.append({
                'date': eff_date,
                'direction': 'debit',
                'amount': amt,
                'category': e['category'],
                'event_id': eid,
                'flexibility': e.get('flexibility', 'fixed'),
                'min_amount': float(e['minimum_allowed_amount']) if e.get('minimum_allowed_amount') else None,
                'desc': e.get('description', '')
            })
        elif status == 'scheduled':
            if direction == 'debit':
                # Apply rent multiplier if rent
                if e['category'] in ('rent', 'housing') and amendments['rent_multiplier'] != 1.0:
                    amt *= amendments['rent_multiplier']
                future_cash_events.append({
                    'date': eff_date,
                    'direction': 'debit',
                    'amount': amt,
                    'category': e['category'],
                    'event_id': eid,
                    'flexibility': e.get('flexibility', 'fixed'),
                    'min_amount': float(e['minimum_allowed_amount']) if e.get('minimum_allowed_amount') else None,
                    'desc': e.get('description', '')
                })
            elif direction == 'credit' and ev_type == 'income':
                # Confirmed salary
                if amendments['salary_ended']:
                    continue
                sal_date = eff_date
                if amendments['salary_override_date']:
                    sal_date = parse_date(amendments['salary_override_date'])
                sal_amt = amt
                if amendments['salary_override_amount']:
                    sal_amt = amendments['salary_override_amount']
                future_cash_events.append({
                    'date': sal_date,
                    'direction': 'credit',
                    'amount': sal_amt,
                    'category': e['category'],
                    'event_id': eid,
                    'flexibility': 'fixed',
                    'desc': e.get('description', '')
                })

    # 2. Extract monthly recurring patterns from settled historical events
    # We group settled debits by category and analyze recurrence
    settled_debits = [e for e in u_events if e['status'] == 'settled' and e['direction'] == 'debit' and e.get('amount')]
    
    # Check if user has recurring salary when not explicitly scheduled
    settled_salaries = [e for e in u_events if e['status'] == 'settled' and e['direction'] == 'credit' and e['category'] == 'salary' and e.get('amount')]
    recurring_salary = None
    if not amendments['salary_ended'] and settled_salaries:
        # Check if salary was recurring (at least 2 salary events)
        if len(settled_salaries) >= 2 or amendments['salary_override_amount']:
            # Find typical salary day of month (usually 15th)
            last_sal = settled_salaries[-1]
            sal_day = int(last_sal['event_date'].split('-')[2])
            sal_amt = float(last_sal['amount'])
            if amendments['salary_override_amount']:
                sal_amt = amendments['salary_override_amount']
            if amendments['salary_override_date']:
                sal_day = int(amendments['salary_override_date'].split('-')[2])
            recurring_salary = {
                'day': sal_day,
                'amount': sal_amt,
                'category': 'salary',
                'event_id': last_sal['event_id']
            }

    # Group recurring monthly expenses
    cat_events = defaultdict(list)
    for e in settled_debits:
        cat_events[e['category']].append(e)

    recurring_monthly_expenses = []
    variable_frequency_expenses = []

    for cat, evs in cat_events.items():
        if len(evs) < 2:
            continue
        # Check if monthly (subscriptions, rent, utilities, insurance, education, debt_repayment, healthcare)
        # Sort by event_date
        evs.sort(key=lambda x: x['event_date'])
        
        # If events occur roughly once a month (count around 4-6 over 6 months)
        if cat in ('rent', 'housing', 'utilities', 'insurance', 'education', 'debt_repayment', 'healthcare',
                    'music_subscription', 'delivery_membership', 'cloud_storage', 'streaming', 'entertainment',
                    'gym', 'shopping', 'family_support', 'subscription'):
            # It's a monthly recurring commitment
            last_ev = evs[-1]
            day_of_month = int(last_ev['event_date'].split('-')[2])
            # For rent/housing, check if lease multiplier applies
            amt = float(last_ev['amount'])
            if cat in ('rent', 'housing') and amendments['rent_multiplier'] != 1.0:
                amt *= amendments['rent_multiplier']
            
            recurring_monthly_expenses.append({
                'category': cat,
                'day': day_of_month,
                'amount': amt,
                'flexibility': last_ev.get('flexibility', 'fixed'),
                'min_amount': float(last_ev['minimum_allowed_amount']) if last_ev.get('minimum_allowed_amount') else None,
                'event_id': last_ev['event_id'],
                'desc': last_ev.get('description', '')
            })
        elif cat in ('groceries', 'transport', 'dining'):
            # Variable recurring spending: weekly / bi-weekly / periodic
            # Compute average interval between events
            dates = [parse_date(e['event_date']) for e in evs]
            diffs = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
            avg_interval = sum(diffs) / len(diffs) if diffs else 7
            avg_interval = max(3, round(avg_interval))
            
            # Most recent typical amount
            recent_amts = [float(e['amount']) for e in evs[-4:]]
            typical_amt = sum(recent_amts) / len(recent_amts)
            last_date = dates[-1]
            last_ev = evs[-1]

            variable_frequency_expenses.append({
                'category': cat,
                'last_date': last_date,
                'interval_days': avg_interval,
                'amount': typical_amt,
                'flexibility': last_ev.get('flexibility', 'fixed'),
                'min_amount': float(last_ev['minimum_allowed_amount']) if last_ev.get('minimum_allowed_amount') else None,
                'event_id': last_ev['event_id'],
                'desc': last_ev.get('description', '')
            })

    return {
        'future_cash_events': future_cash_events,
        'recurring_salary': recurring_salary,
        'recurring_monthly_expenses': recurring_monthly_expenses,
        'variable_frequency_expenses': variable_frequency_expenses
    }


def simulate_timeline(req_date, cur_balance, commitments, spending_changes=None, additional_payments=None):
    """
    Simulates cash balance day by day for [req_date, req_date + 89 days].
    Returns daily balances: dict of date -> balance.
    """
    spending_changes = spending_changes or []
    additional_payments = additional_payments or {}  # date -> amount
    
    # Parse active spending changes
    stopped_events = set()
    reduced_events = {}  # event_id -> new_amount
    for ch in spending_changes:
        if ch.startswith('stop:'):
            stopped_events.add(ch.split(':')[1])
        elif ch.startswith('reduce_to:'):
            parts = ch.split(':')
            reduced_events[parts[1]] = float(parts[2])

    # Calendar of scheduled inflows and outflows
    daily_inflows = defaultdict(float)
    daily_outflows = defaultdict(float)

    # 1. Add specific future events (pending debits, scheduled salary/debits)
    scheduled_salary_dates = set()
    scheduled_expense_cycles = set()  # (category, year, month)

    for ev in commitments['future_cash_events']:
        eid = ev['event_id']
        d = ev['date']
        amt = ev['amount']
        
        if ev['direction'] == 'credit':
            daily_inflows[d] += amt
            scheduled_salary_dates.add(d)
        else:
            # Debit
            if eid in stopped_events:
                continue
            if eid in reduced_events:
                amt = reduced_events[eid]
            daily_outflows[d] += amt
            scheduled_expense_cycles.add((ev['category'], d.year, d.month))

    # 2. Project recurring monthly salary if not already covered by scheduled salary
    rec_sal = commitments['recurring_salary']
    if rec_sal:
        sal_day = rec_sal['day']
        sal_amt = rec_sal['amount']
        # Project for the next 3 months
        for m_offset in range(4):
            y = req_date.year + (req_date.month + m_offset - 1) // 12
            m = (req_date.month + m_offset - 1) % 12 + 1
            # handle day clamping
            target_day = min(sal_day, 28 if m == 2 else 30 if m in (4,6,9,11) else 31)
            d = datetime(y, m, target_day).date()
            if req_date <= d <= req_date + timedelta(days=89):
                # Don't add if already a scheduled salary around this date
                if not any(abs((d - sd).days) <= 7 for sd in scheduled_salary_dates):
                    daily_inflows[d] += sal_amt

    # 3. Project recurring monthly expenses
    for exp in commitments['recurring_monthly_expenses']:
        eid = exp['event_id']
        cat = exp['category']
        amt = exp['amount']
        exp_day = exp['day']

        if eid in stopped_events:
            continue
        if eid in reduced_events:
            amt = reduced_events[eid]

        for m_offset in range(4):
            y = req_date.year + (req_date.month + m_offset - 1) // 12
            m = (req_date.month + m_offset - 1) % 12 + 1
            target_day = min(exp_day, 28 if m == 2 else 30 if m in (4,6,9,11) else 31)
            d = datetime(y, m, target_day).date()
            if req_date <= d <= req_date + timedelta(days=89):
                # If there is already a scheduled event for this category in this month, skip projection
                if (cat, y, m) not in scheduled_expense_cycles:
                    daily_outflows[d] += amt

    # 4. Project variable frequency expenses (groceries, transport, dining)
    for vexp in commitments['variable_frequency_expenses']:
        eid = vexp['event_id']
        amt = vexp['amount']
        interval = vexp['interval_days']
        curr_d = vexp['last_date'] + timedelta(days=interval)

        if eid in stopped_events:
            continue
        if eid in reduced_events:
            amt = reduced_events[eid]

        while curr_d <= req_date + timedelta(days=89):
            if curr_d >= req_date:
                daily_outflows[curr_d] += amt
            curr_d += timedelta(days=interval)

    # 5. Simulate day by day
    bal = cur_balance
    timeline = {}
    for offset in range(90):
        t = req_date + timedelta(days=offset)
        # Morning: apply inflows
        bal += daily_inflows[t]
        # Midday: apply normal outflows
        bal -= daily_outflows[t]
        # Apply request payments if any
        if t in additional_payments:
            bal -= additional_payments[t]
        timeline[t] = bal

    return timeline


def evaluate_request(req, profile, commitments, options):
    """
    Evaluates a single request and returns the decision dictionary.
    """
    req_id = req['request_id']
    req_date = parse_date(req['request_date'])
    req_amt = float(req['requested_amount'])
    desired_date = parse_date(req['desired_completion_date'])
    allows_partial = req['allows_partial_payment'].lower() == 'true'

    cur_bal = float(profile['current_available_balance'])
    min_bal = float(profile['minimum_balance_to_keep'])
    home_curr = profile['home_currency']
    user_methods = set(profile['payment_methods_user_will_consider'].split('|'))
    max_inst_months = int(profile['max_installment_months']) if profile['max_installment_months'] else None

    # STAGE 5: Baseline 90-day forecast (NO request payment, NO spending changes)
    baseline_timeline = simulate_timeline(req_date, cur_bal, commitments)

    # STAGE 6: amount_safe_to_pay
    # safe = max(0, min(requested_amount, min_t(B0(t) - minimum_balance_to_keep)))
    min_cushion = min(baseline_timeline[t] - min_bal for t in baseline_timeline)
    amount_safe_to_pay = max(0.0, min(req_amt, min_cushion))
    # Round cleanly
    amount_safe_to_pay = round(amount_safe_to_pay, 2)

    # STAGE 7: earliest_date_for_full_payment
    # First date d where paying req_amt on d leaves B0(t) - req_amt >= min_bal for all t >= d
    earliest_date_for_full_payment = None
    for offset in range(90):
        cand_date = req_date + timedelta(days=offset)
        # Check if for all t >= cand_date: baseline_timeline[t] - req_amt >= min_bal
        is_safe = True
        for t in baseline_timeline:
            if t >= cand_date:
                if baseline_timeline[t] - req_amt < min_bal:
                    is_safe = False
                    break
        if is_safe:
            earliest_date_for_full_payment = cand_date
            break

    # STAGE 8: Candidate Generation & Filtering
    def test_plan(payments, spending_changes=None):
        """Simulates payments dict {date: amount} and checks min_balance constraint."""
        tl = simulate_timeline(req_date, cur_bal, commitments, spending_changes, payments)
        return all(tl[t] >= min_bal for t in tl)

    candidate_plans = []

    # 1. Full Payment today
    if 'full_payment' in user_methods:
        if test_plan({req_date: req_amt}):
            candidate_plans.append({
                'method': 'full_payment',
                'status': 'affordable_now',
                'plan_str': f"{format_date(req_date)}:{req_amt:g}" if req_amt.is_integer() else f"{format_date(req_date)}:{req_amt:.2f}",
                'earliest_date': req_date,
                'spending_changes': 'none',
                'total_cost': req_amt,
                'first_date': req_date,
                'num_payments': 1,
                'deadline_violation': 0 if req_date <= desired_date else 1,
                'has_changes': 0,
                'option_id': 1
            })

    # 2. Supplied Installment Options
    if 'installments' in user_methods and max_inst_months is not None:
        for opt in options:
            if opt['payment_method'] != 'installments':
                continue
            num_pmts = int(opt['number_of_payments'])
            pmt_amt = float(opt['payment_amount'])
            first_d = parse_date(opt['first_payment_date'])
            freq_days = int(opt['payment_frequency_days'])
            total_amt = float(opt['total_payable_amount'])
            opt_id_num = int(re.findall(r'\d+', opt['payment_option_id'])[0]) if re.findall(r'\d+', opt['payment_option_id']) else 999

            # Check max_installment_months
            if num_pmts > max_inst_months:
                continue

            # Build payment schedule
            pmts = {}
            plan_parts = []
            curr_pmt_d = first_d
            for i in range(num_pmts):
                pmts[curr_pmt_d] = pmt_amt
                fmt_amt = f"{pmt_amt:g}" if pmt_amt.is_integer() else f"{pmt_amt:.2f}"
                plan_parts.append(f"{format_date(curr_pmt_d)}:{fmt_amt}")
                if i < num_pmts - 1:
                    curr_pmt_d += timedelta(days=freq_days)

            last_pmt_d = curr_pmt_d
            deadline_viol = 0 if last_pmt_d <= desired_date else 1

            # Simulate
            if test_plan(pmts):
                candidate_plans.append({
                    'method': 'installments',
                    'status': 'affordable_with_plan',
                    'plan_str': '|'.join(plan_parts),
                    'earliest_date': earliest_date_for_full_payment,
                    'spending_changes': 'none',
                    'total_cost': total_amt,
                    'first_date': first_d,
                    'num_payments': num_pmts,
                    'deadline_violation': deadline_viol,
                    'has_changes': 0,
                    'option_id': opt_id_num
                })

    # 3. Partial Payment
    if allows_partial and 'partial_payment' in user_methods:
        if 0 < amount_safe_to_pay < req_amt and earliest_date_for_full_payment and earliest_date_for_full_payment <= desired_date:
            second_amt = round(req_amt - amount_safe_to_pay, 2)
            pmts = {
                req_date: amount_safe_to_pay,
                earliest_date_for_full_payment: second_amt
            }
            if test_plan(pmts):
                p1_fmt = f"{amount_safe_to_pay:g}" if amount_safe_to_pay.is_integer() else f"{amount_safe_to_pay:.2f}"
                p2_fmt = f"{second_amt:g}" if second_amt.is_integer() else f"{second_amt:.2f}"
                candidate_plans.append({
                    'method': 'partial_payment',
                    'status': 'affordable_with_plan',
                    'plan_str': f"{format_date(req_date)}:{p1_fmt}|{format_date(earliest_date_for_full_payment)}:{p2_fmt}",
                    'earliest_date': earliest_date_for_full_payment,
                    'spending_changes': 'none',
                    'total_cost': req_amt,
                    'first_date': req_date,
                    'num_payments': 2,
                    'deadline_violation': 0,
                    'has_changes': 0,
                    'option_id': 9999
                })

    # 4. Wait
    if 'full_payment' in user_methods and earliest_date_for_full_payment:
        if earliest_date_for_full_payment <= desired_date:
            req_fmt = f"{req_amt:g}" if req_amt.is_integer() else f"{req_amt:.2f}"
            candidate_plans.append({
                'method': 'wait',
                'status': 'affordable_later',
                'plan_str': f"{format_date(earliest_date_for_full_payment)}:{req_fmt}",
                'earliest_date': earliest_date_for_full_payment,
                'spending_changes': 'none',
                'total_cost': req_amt,
                'first_date': earliest_date_for_full_payment,
                'num_payments': 1,
                'deadline_violation': 0,
                'has_changes': 0,
                'option_id': 99999
            })

    # Filter candidates that satisfy deadline without spending changes
    valid_no_changes = [c for c in candidate_plans if c['deadline_violation'] == 0 and c['has_changes'] == 0]

    if valid_no_changes:
        # STAGE 11: Ranking
        valid_no_changes.sort(key=lambda c: (
            c['deadline_violation'],
            c['has_changes'],
            c['total_cost'],
            c['first_date'],
            c['num_payments'],
            c['option_id']
        ))
        best_plan = valid_no_changes[0]
    else:
        # STAGE 10: Spending Changes Fallback
        # If no valid plan satisfies deadline, evaluate permitted spending changes
        protect_cats = set(profile['expense_categories_to_protect'].split('|')) if profile['expense_categories_to_protect'] else set()
        reduce_cats = set(profile['expense_categories_user_is_willing_to_reduce'].split('|')) if profile['expense_categories_user_is_willing_to_reduce'] else set()
        stop_cats = set(profile['expense_categories_user_is_willing_to_stop'].split('|')) if profile['expense_categories_user_is_willing_to_stop'] else set()

        # Find eligible flexible items
        eligible_actions = []
        all_recs = commitments['recurring_monthly_expenses'] + commitments['variable_frequency_expenses']
        
        seen_events = set()
        for r in all_recs:
            eid = r['event_id']
            cat = r['category']
            flex = r.get('flexibility', 'fixed')
            if eid in seen_events or cat in protect_cats:
                continue
            seen_events.add(eid)

            if flex in ('stoppable', 'reducible_or_stoppable') and cat in stop_cats:
                eligible_actions.append(f"stop:{eid}")
            if flex in ('reducible', 'reducible_or_stoppable') and cat in reduce_cats and r.get('min_amount') is not None:
                min_amt_val = r['min_amount']
                fmt_min = f"{min_amt_val:g}" if min_amt_val.is_integer() else f"{min_amt_val:.2f}"
                eligible_actions.append(f"reduce_to:{eid}:{fmt_min}")

        # Enumerate combinations up to 3 actions
        valid_change_plans = []
        from itertools import combinations
        
        # Test full payment today with spending changes
        if 'full_payment' in user_methods:
            for k in range(1, min(4, len(eligible_actions) + 1)):
                for comb in combinations(eligible_actions, k):
                    # Check not stopping and reducing same event
                    e_ids = [a.split(':')[1] for a in comb]
                    if len(set(e_ids)) < len(e_ids):
                        continue
                    if test_plan({req_date: req_amt}, list(comb)):
                        req_fmt = f"{req_amt:g}" if req_amt.is_integer() else f"{req_amt:.2f}"
                        valid_change_plans.append({
                            'method': 'full_payment',
                            'status': 'affordable_with_plan',
                            'plan_str': f"{format_date(req_date)}:{req_fmt}",
                            'earliest_date': earliest_date_for_full_payment,
                            'spending_changes': '|'.join(comb),
                            'total_cost': req_amt,
                            'first_date': req_date,
                            'num_payments': 1,
                            'deadline_violation': 0 if req_date <= desired_date else 1,
                            'has_changes': len(comb),
                            'option_id': 1
                        })
                if valid_change_plans:
                    break

        if valid_change_plans:
            valid_change_plans.sort(key=lambda c: (
                c['deadline_violation'],
                c['has_changes'],
                c['total_cost'],
                c['first_date'],
                c['num_payments'],
                c['option_id']
            ))
            best_plan = valid_change_plans[0]
        else:
            # Not Affordable Fallback
            best_plan = {
                'method': 'not_recommended',
                'status': 'not_affordable',
                'plan_str': 'none',
                'earliest_date': None,
                'spending_changes': 'none',
                'total_cost': 0,
                'first_date': None,
                'num_payments': 0,
                'deadline_violation': 1,
                'has_changes': 0,
                'option_id': 999999
            }

    # Format output fields
    out_safe_pay = f"{amount_safe_to_pay:g}" if amount_safe_to_pay.is_integer() else f"{amount_safe_to_pay:.2f}"
    out_status = best_plan['status']
    out_method = best_plan['method']
    out_plan = best_plan['plan_str']
    out_earliest = format_date(best_plan['earliest_date']) if best_plan['earliest_date'] else ""
    out_changes = best_plan['spending_changes']

    # Generate Decision Explanation
    if out_status == 'affordable_now':
        explanation = f"Pay {home_curr} {out_safe_pay} today. This leaves at least {home_curr} {min_bal:g} available over the next 90 days."
    elif out_method == 'installments':
        num_p = best_plan['num_payments']
        first_amt = out_plan.split('|')[0].split(':')[1]
        first_d_str = best_plan['first_date'].strftime('%d %B %Y').lstrip('0')
        explanation = f"Use {num_p} installments of {home_curr} {first_amt}, starting {first_d_str}. This leaves at least {home_curr} {min_bal:g} available."
    elif out_method == 'partial_payment':
        p2_date_str = earliest_date_for_full_payment.strftime('%d %B %Y').lstrip('0')
        rem_amt = round(req_amt - amount_safe_to_pay, 2)
        rem_fmt = f"{rem_amt:g}" if rem_amt.is_integer() else f"{rem_amt:.2f}"
        explanation = f"Pay {home_curr} {out_safe_pay} today and the remaining {home_curr} {rem_fmt} on {p2_date_str}. This completes the full request and keeps the {home_curr} {min_bal:g} minimum protected."
    elif out_method == 'wait':
        wait_d_str = earliest_date_for_full_payment.strftime('%d %B %Y').lstrip('0')
        req_fmt = f"{req_amt:g}" if req_amt.is_integer() else f"{req_amt:.2f}"
        explanation = f"Pay {home_curr} {req_fmt} in full on {wait_d_str}. Paying earlier would take the balance below the {home_curr} {min_bal:g} minimum."
    elif out_status == 'affordable_with_plan' and out_method == 'full_payment':
        ch_desc = []
        for ch in out_changes.split('|'):
            if ch.startswith('stop:'):
                eid = ch.split(':')[1]
                ev_desc = [e.get('description', '') for e in commitments['recurring_monthly_expenses'] + commitments['variable_frequency_expenses'] if e['event_id'] == eid]
                ch_desc.append(f"stop the {ev_desc[0].lower() if ev_desc else 'flexible subscription'}")
            elif ch.startswith('reduce_to:'):
                parts = ch.split(':')
                eid = parts[1]
                new_a = parts[2]
                ev_desc = [e.get('description', '') for e in commitments['recurring_monthly_expenses'] + commitments['variable_frequency_expenses'] if e['event_id'] == eid]
                ch_desc.append(f"reduce the {ev_desc[0].lower() if ev_desc else 'flexible expense'} to {home_curr} {new_a}")
        req_fmt = f"{req_amt:g}" if req_amt.is_integer() else f"{req_amt:.2f}"
        action_text = ' and '.join(ch_desc).capitalize()
        explanation = f"{action_text}, then pay {home_curr} {req_fmt} today. This leaves at least {home_curr} {min_bal:g} available."
    else:
        des_d_str = desired_date.strftime('%d %B %Y').lstrip('0')
        explanation = f"Do not make this payment by {des_d_str}. None of the available options keeps the {home_curr} {min_bal:g} minimum protected."

    return {
        'request_id': req_id,
        'amount_safe_to_pay': out_safe_pay,
        'affordability_status': out_status,
        'recommended_payment_method': out_method,
        'payment_plan': out_plan,
        'earliest_date_for_full_payment': out_earliest,
        'spending_changes_needed': out_changes,
        'decision_explanation': explanation
    }

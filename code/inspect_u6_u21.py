#!/usr/bin/env python3
import sys
sys.path.insert(0, 'code')
import csv
from decimal import Decimal

profiles = {r['user_id']: r for r in csv.DictReader(open('dataset/financial_profiles.csv'))}
p6 = profiles['user_06']
p21 = profiles['user_21']

print('user_06: bal=', p6['current_available_balance'], 'min=', p6['minimum_balance_to_keep'])
# margin = 1942.4 - 800 = 1142.4.
# safe expected = 603.3.
# diff = 1142.4 - 603.3 = 539.10.

print('user_21: bal=', p21['current_available_balance'], 'min=', p21['minimum_balance_to_keep'])
# margin = 3911.35 - 1800 = 2111.35.
# safe expected = 1543.35.
# diff = 2111.35 - 1543.35 = 568.00.

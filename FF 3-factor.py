##########################################
# Fama French 3-Factor Model
# Jan 2022
# Modified by Ziran Zuo
##########################################

# import packages
import pandas as pd
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
from dateutil.relativedelta import *
from pandas.tseries.offsets import *
from scipy import stats


######################################################################################################################
# Part 1 Compustat data

# Please read the original paper of Fama and French (1993) before you replicate the paper
# The sample period starts from 1961 and the first month of the factor return is July 1963

# Some variable definition:
# 1. Book common equity (book value): "We define book common equity, BE, as the Compustat  book value of
# stockholders' equity, plus balance-sheet deferred taxes and investment tax credit (if available), minus the book value
# of preferred stock. Depending on availability, we use the redemption, liquidation, or par value (in that order) to
# estimate the value of preferred stock" (Fama and French, 1993)

# 2. "We do not use negative-BE firms"

# 3. To avoid the survival bias inherent in the way Computstat adds firms to its tapes (Banz and Breen (1986),
# we do not include firms until they have appeared on Compustat for two years."

# Compustat variables:
# AT = Total Assets
# SEQ = Total Parent Stockholders' Equity
# TXDITC = Deferred Taxes and Investment Tax Credit
# PSTKRV = Preferred Stock Redemption Value
# PSTKL = Preferred Stock Liquidating Value
# PSTK = Preferred/Preference Stock (Capital) - Total
######################################################################################################################


# Import data (Please declare your path when you import data --> the place you store the data)

#comp = pd.read_csv('D:/PycharmProjects/ACF602/Empirical Asset pricing/crsp_comp_merged.csv')

comp = pd.read_csv('/Users/lesliezhan/Desktop/602/FF 3-factor Model (Week 13-14)-20220224/crsp_comp_merged.csv')


# covert date to pandas date format
comp['datadate'] = comp['datadate'].astype(str)
comp['datadate'] = pd.to_datetime(comp['datadate'])

# Generate the calendar year of datadate
comp['year'] = comp['datadate'].dt.year

# Create preferrerd stock --> The order is pstkrv> pstkl> pstk
comp['ps'] = np.where(comp['pstkrv'].isnull(), comp['pstkl'], comp['pstkrv'])
comp['ps'] = np.where(comp['ps'].isnull(), comp['pstk'], comp['ps'])
comp['ps'] = np.where(comp['ps'].isnull(), 0, comp['ps'])

# Replace missing txditc with zero
comp['txditc'] = comp['txditc'].fillna(0)

# Create book equity --> Book value of equity cannot be negative
comp['be'] = comp['seq'] + comp['txditc'] - comp['ps']
comp['be'] = np.where(comp['be'] > 0, comp['be'], np.nan)


# Number of years in Compustat --> how many years the firm appear in compustat (firm age)
comp = comp.sort_values(by=['LPERMNO', 'datadate'])
comp['count'] = comp.groupby(['LPERMNO']).cumcount()  # Note that this starts from zero

# Some companies change fiscal year end in the middle of the calendar year
# In these cases, there are more than one annual record for accounting data
# We need to select the last annual record in a given calendar year
comp = comp.sort_values(by=['LPERMNO', 'year', 'datadate'])
comp = comp.drop_duplicates(subset=['LPERMNO', 'year'], keep='last')

# keep necessary variables and rename for future matching
comp = comp[['LPERMNO', 'GVKEY', 'datadate', 'year', 'be', 'count']].rename(columns={'LPERMNO': 'PERMNO'})

#################################################################################################################
# Part 2 CRSP data

# Downloading variables from CRSP Monthly stock

# CRSP Variables:
# RET: Holding period return
# PRC: The closing price
# SHROUT: The number of publicly held shares, recorded in thousands
# SHRCD: Share code
# EXCHCD: Exchange code
# DLRET: Delisting return
#################################################################################################################

# Import crsp data
#crsp_m = pd.read_csv('D:/PycharmProjects/ACF602/Empirical Asset pricing/crsp.csv')

crsp_m = pd.read_csv('/Users/lesliezhan/Desktop/602/FF 3-factor Model (Week 13-14)-20220224/crsp.csv')

# Filter data

# The stock exchanges are NYSE(exchange code=1), AMEX(2) and NASDAQ(3)
crsp_m = crsp_m[crsp_m['EXCHCD'].isin([1, 2, 3])]

# Only keep common shares --> share code=10 and 11
crsp_m = crsp_m[crsp_m['SHRCD'].isin([10, 11])]

# Drop missing returns

# Remove string value from numerical return column (e.g., B and C) --> They represent errors
crsp_m['RET'] = pd.to_numeric(crsp_m['RET'], errors='coerce')  # Covert string value to missing value
crsp_m = crsp_m[crsp_m['RET'].notnull()]

# Change variable format to int
crsp_m[['PERMNO', 'PERMCO', 'SHRCD', 'EXCHCD']] = crsp_m[['PERMNO', 'PERMCO', 'SHRCD', 'EXCHCD']].astype(int)

# Covert the data to pandas date format and line up the date to the end of month
crsp_m['date'] = crsp_m['date'].astype(str)
crsp_m['date'] = pd.to_datetime(crsp_m['date'])
crsp_m['jdate'] = crsp_m['date'] + MonthEnd(0)

# Generate adjusted return by considering the delisting return
crsp_m['DLRET'] = pd.to_numeric(crsp_m['DLRET'], errors='coerce')  # Covert string value to missing value
crsp_m['DLRET'] = crsp_m['DLRET'].fillna(0)
crsp_m['RET_ADJ'] = (1 + crsp_m['RET']) * (1 + crsp_m['DLRET']) - 1

# Generate market value (in millions)
crsp_m['me'] = crsp_m['PRC'].abs() * crsp_m['SHROUT'] / 1000  # Price can be negative if is the average of bid and ask

# Sort values and keep necessary variables
crsp_m = crsp_m.sort_values(by=['PERMCO', 'jdate'])
crsp = crsp_m.drop(['DLRET', 'PRC', 'SHROUT', 'RET', 'SHRCD'], axis=1)  # axis=1 refers to column

# Aggregate market cap at firm level --> One firm may have multiple classes of stocks (multiple permnos). In this case,
# we need to aggregate the market cap of all stocks belonging to the firm
# The aggregated market cap will be assigned to the permno with the largest market cap

# Permco: 123 --> Stock Class A: Permno: 10001 2 million / Stock Class B: Permno: 10002 1 million

# Permno 10001 : market cap --> 3 million

# Sum of me across different permnos belonging to the same permco in a given date
crsp_summe = crsp.groupby(['jdate', 'PERMCO'])['me'].sum().reset_index()

# Largest market cap within a permco in a given date
crsp_maxme = crsp.groupby(['jdate', 'PERMCO'])['me'].max().reset_index()

# Join by jdate/maxme to find the permno --> find the permno which has the largest market cap under one permco
crsp1 = pd.merge(crsp, crsp_maxme, how='inner', on=['jdate', 'PERMCO', 'me'])

# Drop me column and replace with the sum me
crsp1 = crsp1.drop(['me'], axis=1)

# Join with sum of me to get the correct market cap info
crsp2 = pd.merge(crsp1, crsp_summe, how='inner', on=['jdate', 'PERMCO'])

# Sort by permno and date and also drop duplicates
crsp2 = crsp2.sort_values(by=['PERMNO', 'jdate']).drop_duplicates()


# keep December market cap -> When we calculate value factor (B/M)
# we use the market cap on December in prior year
crsp2['year'] = crsp2['jdate'].dt.year
crsp2['month'] = crsp2['jdate'].dt.month
decme = crsp2[crsp2['month'] == 12]
decme = decme[['PERMNO', 'jdate', 'me']].rename(columns={'me': 'dec_me', 'jdate': 'ffdate'})

# Generate July to June dates --> To make the ffyear is from July of yeat t to June of year t+1
# Our portfolios are rebalanced on each June
# Jan - December (calendar year) --> July - June (ff year) (e.g., 202001 - 202012 --> 201907 - 202006)
crsp2['ffdate'] = crsp2['jdate'] + MonthEnd(-6)
crsp2['ffyear'] = crsp2['ffdate'].dt.year
crsp2['ffmonth'] = crsp2['ffdate'].dt.month

# Generate the market cap of prior month as the portfolio weight (value-weighted portfolio)
crsp2['lme'] = crsp2.groupby(['PERMNO'])['me'].shift(1)  # lagged variable

# Create a dataset in each June (Portfolio forming month) merged with market cap from previous December
# Because there is at least 6 month gap for accounting information to be incorporated into stock price

# Keep only the data on June --> Portfolios are sorted on June of each year
crsp3 = crsp2[crsp2['month'] == 6]

# merge with market cap in last December --> 20190630 <--> 20181231
crspjune = pd.merge(crsp3, decme, how='left', on=['PERMNO', 'ffdate'])

#################################################################################################################
# Part 3 Merge CRSP with Compustat data on June of each year (Hard to understand but very important)

# Match fiscal year ending calendar year t (compustat) with June t+1 (crsp)
# --> All portfolios are formed on June t+1
# Why? --> Fama argues that it may take at least 6 months for accounting information to be incorporated into stock
# price or return
# For example, the datadate of accounting information for firm A is 20180930, we should start to use on 20190630
# In a nutshell, we should convert the datadate to the end of the year and then add 6 month
# e.g, 20180930 --> 20181231 --> 20190630)
#################################################################################################################

# Prepare compustat data for matching
comp['jdate'] = comp['datadate'] + YearEnd(0)
comp['jdate'] = comp['jdate'] + MonthEnd(6)

# keep necessary variables in Compustat
comp2 = comp[['PERMNO', 'jdate', 'be', 'count']]

# keep necessary variables in crspjune
crspjune2 = crspjune[['PERMNO', 'PERMCO', 'jdate', 'RET_ADJ', 'me', 'lme', 'dec_me', 'EXCHCD']]

# Merge the crspjune2 and compustat2
ccm_june = pd.merge(crspjune, comp2, how='inner', on=['PERMNO', 'jdate'])

# Generate book to market ratio (B/M)
ccm_june['beme'] = ccm_june['be'] / ccm_june['dec_me']

######################################################################################################################
#  Part 4 Assign size breakdown and value breakdown to stock

#  Forming Portolios by ME and BEME as of each June
#  Calculate NYSE Breakpoints (size factor) for Market Equity (ME) and  Book-to-Market (BEME)
#  Note that we only use the stocks in NYSE to define the "big" and "small" stock / "value" and "growth" stock (median)
######################################################################################################################

# Select NYSE stocks for bucket breakdown
# exchcd = 1 and positive beme and positive me and at least 2 years in comp
nyse = ccm_june[(ccm_june['EXCHCD'] == 1) & (ccm_june['beme'] > 0) & (ccm_june['me'] > 0) & (ccm_june['count'] > 1)]

# Size breakdown
nyse_sz = nyse.groupby(['jdate'])['me'].median().to_frame().reset_index().rename(columns={'me': 'sizemedn'})

# BEME breakdown
nyse_bm = nyse.groupby(['jdate'])['beme'].describe(percentiles=[0.3, 0.7]).reset_index()
nyse_bm = nyse_bm[['jdate', '30%', '70%']].rename(columns={'30%': 'bm30', '70%': 'bm70'})

# calculate the OP breakdown and investment breakdown

# Merge size and BEME breakdown
nyse_breaks = pd.merge(nyse_sz, nyse_bm, how='inner', on=['jdate'])

# Join back size and beme breakdown
ccm_june2 = pd.merge(ccm_june, nyse_breaks, how='left', on=['jdate'])


#####################################################
# Two small functions to define types
# functions to assign sz and bm bucket
def sz_bucket(row):
    if row['me'] == np.nan:
        value = ''
    elif row['me'] <= row['sizemedn']:
        value = 'S'
    else:
        value = 'B'
    return value


def bm_bucket(row):
    if 0 <= row['beme'] <= row['bm30']:
        value = 'L'
    elif row['beme'] <= row['bm70']:
        value = 'M'
    elif row['beme'] > row['bm70']:
        value = 'H'
    else:
        value = ''
    return value

# op and investment --> they could be negative

def bm_bucket(row):
    if row['beme'] <= row['bm30']:
        value = 'L'
    elif row['beme'] <= row['bm70']:
        value = 'M'
    elif row['beme'] > row['bm70']:
        value = 'H'
    else:
        value = ''
    return value

###################################################

# Assign size portfolio
ccm_june2['szport'] = np.where((ccm_june2['beme'] > 0) & (ccm_june2['me'] > 0) & (ccm_june2['count'] >= 1),
                               ccm_june2.apply(sz_bucket, axis=1), '')

# Assign book-to-market portfolio
ccm_june2['bmport'] = np.where((ccm_june2['beme'] > 0) & (ccm_june2['me'] > 0) & (ccm_june2['count'] >= 1),
                               ccm_june2.apply(bm_bucket, axis=1), '')

# Create positivebmeme and nonmissport variable
ccm_june2['posbm'] = np.where((ccm_june2['beme'] > 0) & (ccm_june2['me'] > 0) & (ccm_june2['count'] >= 1), 1, 0)
ccm_june2['nonmissport'] = np.where((ccm_june2['bmport'] != ''), 1, 0)

# Store portfolio assignment as of June
june = ccm_june2[['PERMNO', 'jdate', 'bmport', 'szport', 'posbm', 'nonmissport']]
june['ffyear'] = june['jdate'].dt.year

# Merge back with monthly records
crsp4 = crsp2[['date', 'PERMNO', 'RET_ADJ', 'me', 'lme', 'ffyear', 'jdate']]
ccm = pd.merge(crsp4,
               june[['PERMNO', 'ffyear', 'szport', 'bmport', 'posbm', 'nonmissport']], how='left',
               on=['PERMNO', 'ffyear'])


#################################################################################################################
# Part 5 Forming size and value factors and evaluate our replicated results

# Calculate monthly time series of value weighted average portfolio returns
# Value-weighted portfolios means the number of stocks we buy or sell depends on their market cap in prior month
#################################################################################################################

# Function to calculate value weighted return
def wavg(group, avg_name, weight_name):
    d = group[avg_name]
    w = group[weight_name]
    try:
        return (d * w).sum() / w.sum()
    except ZeroDivisionError:
        return np.nan

# Stock1 : 1% 2m / Stock2: 2% 1m / Stock3: 5% 2m --> 1% * 2m + 2% * 1m + 5% * 2m / (2m+1m+2m)= 2+2+10/5=14/5=2.8%


# Value-weighted --> return*lagged market cap/total lagged market cap for all stocks in the portfolio in a given month

# Value-weigthed return
vwret = ccm.groupby(['jdate', 'szport', 'bmport']).apply(wavg, 'RET_ADJ', 'lme').to_frame().reset_index() \
    .rename(columns={0: 'vwret'})
vwret['sbport'] = vwret['szport'] + vwret['bmport']

# Firm count --> How many firms in one portfolio in a given month (jdate)
vwret_n = ccm.groupby(['jdate', 'szport', 'bmport'])['RET_ADJ'].count().reset_index().rename(
    columns={'RET_ADJ': 'n_firms'})
vwret_n['sbport'] = vwret_n['szport'] + vwret_n['bmport']  # 2 X 3 symbols or indicators SH/SL/SM/BH/BL/BM


# Transpose the data
ff_factors = vwret.pivot(index='jdate', columns='sbport', values='vwret').reset_index()
ff_nfirms = vwret_n.pivot(index='jdate', columns='sbport', values='n_firms').reset_index()

# Create SMB and HML factors  two more factors --> RMW, CWA
ff_factors['WH'] = (ff_factors['BH'] + ff_factors['SH']) / 2  # (Big value+Small value)/2
ff_factors['WL'] = (ff_factors['BL'] + ff_factors['SL']) / 2  # (Big growth+Small growth)/2
ff_factors['WHML'] = ff_factors['WH'] - ff_factors['WL']  # Value factor

ff_factors['WB'] = (ff_factors['BL'] + ff_factors['BM'] + ff_factors['BH']) / 3  # (Big low+Big medium+Big high)/3
ff_factors['WS'] = (ff_factors['SL'] + ff_factors['SM'] + ff_factors['SH']) / 3  # (Small low+Small medium+Small high)/3
ff_factors['WSMB'] = ff_factors['WS'] - ff_factors['WB']  # Size factor
ff_factors = ff_factors.rename(columns={'jdate': 'date'})

# n firm count --> How many firms in the portfolio
ff_nfirms['H'] = ff_nfirms['SH'] + ff_nfirms['BH']
ff_nfirms['L'] = ff_nfirms['SL'] + ff_nfirms['BL']
ff_nfirms['HML'] = ff_nfirms['H'] + ff_nfirms['L']

ff_nfirms['B'] = ff_nfirms['BL'] + ff_nfirms['BM'] + ff_nfirms['BH']
ff_nfirms['S'] = ff_nfirms['SL'] + ff_nfirms['SM'] + ff_nfirms['SH']
ff_nfirms['SMB'] = ff_nfirms['B'] + ff_nfirms['S']
ff_nfirms['TOTAL'] = ff_nfirms['SMB']
ff_nfirms = ff_nfirms.rename(columns={'jdate': 'date'})

# Evaluate the replication work --> test the correlation with constructed factors

# Import the downloaded constructed factors from French data library or WRDS
#ff3 = pd.read_csv('D:/PycharmProjects/ACF602/Empirical Asset pricing/FF3.csv')

ff3 = pd.read_csv('/Users/lesliezhan/Desktop/602/FF 3-factor Model (Week 13-14)-20220224/FF3.CSV')

# Make the datasets consistent with our sample period --> 196307 to 202012
ff3 = ff3[['date', 'SMB', 'HML']]

# Generate year and month based on date
ff3['date'] = ff3['date'].astype(str)
ff3['year'] = ff3['date'].str[:4]  # first 4 digits --> from 0 to 3 excluding 4
ff3['month'] = ff3['date'].str[4:]  # excluding 4 --> last two digits
ff3[['year', 'month']] = ff3[['year', 'month']].astype(int)

# Filter sample from 196307-202012
ff3 = ff3[(ff3['year'] <= 2020) & (ff3['year'] >= 1963)]
ff3 = ff3.drop(ff3[(ff3['year'] == 1963) & (ff3['month'] <= 6)].index).reset_index()

# Clean our replicated results for matching
ff_factors['year'] = ff_factors['date'].dt.year
ff_factors['month'] = ff_factors['date'].dt.month

# Filter sample from 196307-202012
ff_factors = ff_factors[(ff_factors['year'] <= 2020) & (ff_factors['year'] >= 1963)]
ff_factors = ff_factors.drop(ff_factors[(ff_factors['year'] == 1963) & (ff_factors['month'] <= 6)].index).reset_index()

# Merge constructed factors and replicated factors
factor = pd.merge(ff_factors[['year', 'month', 'WSMB', 'WHML']], ff3, how='left', on=['year', 'month'])
factor['SMB'] = factor['SMB'] / 100
factor['HML'] = factor['HML'] / 100

# Test the correlation between constructed factors and our replicated factors
SMB_corr = factor['WSMB'].corr(factor['SMB'])
HML_corr = factor['WHML'].corr(factor['HML'])
print(SMB_corr, HML_corr)  # 0.99 for size factor and 0.97 for value factor

# For most replicated factors, we should make sure that our correlation is at least higher than 0.95

# We can also have a simple line chart to see the correlation and evaluate our replication work
factor.plot(x='date', y=['SMB', 'WSMB'])
factor.plot(x='date', y=['HML', 'WHML'])
plt.show()  # show the graphs
-- Migration 0008: a company's financial statements, by reporting period.
--
-- Adds the four tables of ADR 0029. `reporting_period` holds each date a
-- company's statements are drawn up to, with their one currency. The three
-- statement tables hang off it, so a statement cannot exist without its
-- currency: `income_statement` and `cash_flow_statement` are keyed by the
-- period and its length in months, `balance_sheet` by the period alone, as a
-- snapshot has no length. Only the figures the QARP screen reads get a
-- column.
--
-- The tables are STRICT: an amount is a whole number, and a floating-point
-- one is refused rather than stored. An empty cell means "not reported".
-- The figures that cannot be negative are the same list the load empties
-- (ADR 0030), and a test holds the two together.
--
-- On an existing database the four tables start empty, and nothing else
-- changes. `pyvalue fundamentals load` fills them.
--
-- Once applied, this file is never edited (ADR 0007). A change to the schema
-- is a new migration.

CREATE TABLE reporting_period (
    company_id INTEGER NOT NULL REFERENCES company (company_id) ON DELETE RESTRICT,
    -- IS, not =: date() of a malformed text is NULL, and a comparison with
    -- NULL does not fail a CHECK.
    period_end TEXT NOT NULL CHECK (period_end IS date(period_end)),
    currency   TEXT NOT NULL CHECK (currency GLOB '[A-Z][A-Z][A-Z]'),
    PRIMARY KEY (company_id, period_end)
) STRICT;

CREATE TABLE income_statement (
    company_id       INTEGER NOT NULL,
    period_end       TEXT NOT NULL,
    months           INTEGER NOT NULL CHECK (months IN (3, 6, 9, 12)),
    revenue          INTEGER,
    cost_of_revenue  INTEGER CHECK (cost_of_revenue >= 0),
    gross_profit     INTEGER,
    operating_income INTEGER,
    pretax_income    INTEGER,
    income_tax       INTEGER,
    net_income       INTEGER,
    interest_expense INTEGER CHECK (interest_expense >= 0),
    PRIMARY KEY (company_id, period_end, months),
    FOREIGN KEY (company_id, period_end)
        REFERENCES reporting_period (company_id, period_end) ON DELETE RESTRICT,
    CHECK (coalesce(revenue, cost_of_revenue, gross_profit, operating_income, pretax_income,
                    income_tax, net_income, interest_expense) IS NOT NULL)
) STRICT;

CREATE TABLE cash_flow_statement (
    company_id                INTEGER NOT NULL,
    period_end                TEXT NOT NULL,
    months                    INTEGER NOT NULL CHECK (months IN (3, 6, 9, 12)),
    operating_cash_flow       INTEGER,
    capital_expenditure       INTEGER CHECK (capital_expenditure >= 0),
    depreciation_amortization INTEGER CHECK (depreciation_amortization >= 0),
    dividends_paid            INTEGER CHECK (dividends_paid >= 0),
    net_share_sales           INTEGER,
    PRIMARY KEY (company_id, period_end, months),
    FOREIGN KEY (company_id, period_end)
        REFERENCES reporting_period (company_id, period_end) ON DELETE RESTRICT,
    CHECK (coalesce(operating_cash_flow, capital_expenditure, depreciation_amortization,
                    dividends_paid, net_share_sales) IS NOT NULL)
) STRICT;

CREATE TABLE balance_sheet (
    company_id                      INTEGER NOT NULL,
    period_end                      TEXT NOT NULL,
    total_assets                    INTEGER CHECK (total_assets > 0),
    total_liabilities               INTEGER CHECK (total_liabilities >= 0),
    equity                          INTEGER,
    minority_interest               INTEGER,
    cash                            INTEGER CHECK (cash >= 0),
    short_term_investments          INTEGER CHECK (short_term_investments >= 0),
    cash_and_short_term_investments INTEGER CHECK (cash_and_short_term_investments >= 0),
    short_term_debt                 INTEGER CHECK (short_term_debt >= 0),
    long_term_debt                  INTEGER CHECK (long_term_debt >= 0),
    total_debt_stated               INTEGER CHECK (total_debt_stated >= 0),
    lease_obligations               INTEGER CHECK (lease_obligations >= 0),
    current_assets                  INTEGER CHECK (current_assets >= 0),
    current_liabilities             INTEGER CHECK (current_liabilities >= 0),
    noncurrent_liabilities          INTEGER CHECK (noncurrent_liabilities >= 0),
    shares_outstanding              INTEGER CHECK (shares_outstanding > 0),
    PRIMARY KEY (company_id, period_end),
    FOREIGN KEY (company_id, period_end)
        REFERENCES reporting_period (company_id, period_end) ON DELETE RESTRICT,
    CHECK (coalesce(total_assets, total_liabilities, equity, minority_interest, cash,
                    short_term_investments, cash_and_short_term_investments, short_term_debt,
                    long_term_debt, total_debt_stated, lease_obligations, current_assets,
                    current_liabilities, noncurrent_liabilities, shares_outstanding) IS NOT NULL)
) STRICT;

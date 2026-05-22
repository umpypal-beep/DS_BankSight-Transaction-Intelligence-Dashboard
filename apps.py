import os
import sys
import pandas as pd
import sqlite3
from pathlib import Path
import datetime
# ---------------------- Database Setup ----------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "bankdata.db")
CSV_PATHS = {
    "accounts": str(BASE_DIR / "accounts.csv"),
    "branches": str(BASE_DIR / "branches.csv"),
    "customers": str(BASE_DIR / "customers.csv"),
    "loans": str(BASE_DIR / "loans.csv"),
    "support_tickets": str(BASE_DIR / "support_tickets.csv"),
    "transactions": str(BASE_DIR / "transactions.csv"),
}

# Try to import streamlit; if not available, we fall back to a CLI mode.
USE_STREAMLIT = True
try:
    import streamlit as st
except Exception:
    USE_STREAMLIT = False


# Connection cache
_CONN: sqlite3.Connection | None = None


def get_conn() -> Connection:
    global _CONN
    if _CONN is None:
        Path(os.path.dirname(DB_PATH)).mkdir(parents=True, exist_ok=True)
        _CONN = sqlite3.connect(DB_PATH, check_same_thread=False)
    return _CONN


def init_db_from_csvs(force_reload: bool = False):
    """Load CSVs into SQLite if tables don't exist or if force_reload=True."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing = {r[0] for r in cur.fetchall()}

    for name, path in CSV_PATHS.items():
        if force_reload or name not in existing:
            try:
                if not os.path.exists(path):
                    print(f"Warning: CSV not found: {path}")
                    continue
                df = pd.read_csv(path)
                df.columns = [c.strip().replace(' ', '_') for c in df.columns]
                df.to_sql(name, conn, if_exists='replace', index=False)
                print(f"Loaded {name} from {path} ({len(df)} rows)")
            except Exception as e:
                if USE_STREAMLIT:
                    st.warning(f"Could not load {path}: {e}")
                else:
                    print(f"Could not load {path}: {e}")
    conn.commit()


def list_tables():
    conn = get_conn()
    q = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    return [r[0] for r in conn.execute(q).fetchall()]


def read_table(name: str, limit: int = 1000) -> pd.DataFrame:
    if not name:
        return pd.DataFrame()
    tables = list_tables()
    if name not in tables:
        print(f"Table {name} not found. Available: {tables}")
        return pd.DataFrame()
    conn = get_conn()
    sql = f'SELECT * FROM "{name}" LIMIT {int(limit)};'
    return pd.read_sql_query(sql, conn)


def get_schema(name: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({name});")
    rows = cur.fetchall()
    return rows


def run_sql(sql: str) -> pd.DataFrame:
    conn = get_conn()
    try:
        df = pd.read_sql_query(sql, conn)
        return df
    except Exception as e:
        if USE_STREAMLIT:
            st.error(f"SQL error: {e}")
        else:
            print(f"SQL error: {e}")
        return pd.DataFrame()


def insert_row(table: str, row: dict):
    conn = get_conn()
    cols = ",".join(row.keys())
    placeholders = ",".join(["?" for _ in row])
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders});"
    conn.execute(sql, list(row.values()))
    conn.commit()


def update_row(table: str, pk_col: str, pk_val, updates: dict):
    conn = get_conn()
    set_clause = ",".join([f"{k}=?" for k in updates.keys()])
    sql = f"UPDATE {table} SET {set_clause} WHERE {pk_col} = ?;"
    params = list(updates.values()) + [pk_val]
    conn.execute(sql, params)
    conn.commit()


def delete_row(table: str, pk_col: str, pk_val):
    conn = get_conn()
    sql = f"DELETE FROM {table} WHERE {pk_col} = ?;"
    conn.execute(sql, (pk_val,))
    conn.commit()


# ---------------------- App Logic ----------------------
init_db_from_csvs()

if USE_STREAMLIT:
    st.set_page_config(page_title="Bank Dashboard", layout="wide")
    st.title("🏦 BankSight: Transaction Intelligence Dashboard")
    menu = st.sidebar.selectbox("Navigation", [
        "🏠 Introduction",
        "📊 View Tables",
        "🔍 Filter Data",
        "✏️ CRUD Operations",
        "💰 Credit / Debit Simulation",
        "🧠 Analytical Insights",
        "👩‍💻 About Creator",
    ])

    # ---------- Introduction ----------
    if menu == "🏠 Introduction":
        st.header("Project Overview")
        st.markdown(
            """
            BankSight is a financial analytics system built using Python,Streamlit and SQLite3. It allows user to \n
            explore Customer,Account,Transaction,Loan and Support Data,perform CRUD operations,simulate\n
            deposits/withdrawls, and view analytic insights.
            """
            )
        st.header("Objectives :")
        st.markdown(
            """
            • Understand customer & transactions behaviour.\n
            • Detect anomalies and potential fraud.\n 
            • Enable CRUD operations on all datasets.\n 
            • Simulate banking transactions (Credit/Debit).
"""
        )

    # ---------- View Tables ----------
    if menu == "📊 View Tables":
        st.header("📊 View Tables")
        tables = list_tables()
        if not tables:
            st.warning("No tables found in the database. Make sure CSVs are loaded.")
            st.write("CSV availability:", {k: os.path.exists(p) for k, p in CSV_PATHS.items()})
        else:
            sel = st.selectbox("Select a table to view", tables)
            lim = st.number_input("Rows to show", min_value=10, max_value=5000, value=200, step=10)
            df = read_table(sel, limit=lim)
            if df.empty:
                st.info(f"No rows in table `{sel}`.")
            else:
                st.dataframe(df)
            if st.button("Refresh Tables"):
                init_db_from_csvs(force_reload=True)
                st.experimental_rerun()

    # ---------- Filter Data (simpler, pandas-based) ----------
    if menu == "🔍 Filter Data":
        st.header("🔍 Filter Data")
        tables = list_tables()

        if not tables:
            st.warning("No tables found in the database. Make sure CSVs are loaded.")
            st.write("CSV availability:", {k: os.path.exists(p) for k, p in CSV_PATHS.items()})
        else:
            table = st.selectbox("Choose dataset", tables)
            # Load full table once (adjust limit if tables are huge)
            df_full = read_table(table, limit=1000000)
            if df_full.empty:
                st.info("Selected table is empty.")
            else:
                # Choose visible columns
                cols = list(df_full.columns)
                chosen_cols = st.multiselect("Columns to show", cols, default=cols[:8])

                # Build filters interactively (single-column-at-a-time simple flow)
                st.markdown("**Add a filter (you can add multiple in sequence)**")
                # We'll store filters in session_state so they persist across reruns
                if "filters" not in st.session_state:
                    st.session_state.filters = []

                col_to_filter = st.selectbox("Select column to add a filter for", ["— none —"] + cols, key="filter_col")
                if col_to_filter and col_to_filter != "— none —":
                    series = df_full[col_to_filter]
                    # detect type and show an appropriate widget
                    if pd.api.types.is_numeric_dtype(series):
                        lo = float(series.min())
                        hi = float(series.max())
                        sel_range = st.slider(f"Range for {col_to_filter}", lo, hi, value=(lo, min(hi, lo + (hi-lo)*0.1)))
                        if st.button("Add numeric filter"):
                            st.session_state.filters.append(("numeric", col_to_filter, float(sel_range[0]), float(sel_range[1])))
                    elif pd.api.types.is_datetime64_any_dtype(series) or pd.to_datetime(series, errors="coerce").notna().any():
                        try:
                            s_dt = pd.to_datetime(series, errors="coerce")
                            dmin = s_dt.min().date()
                            dmax = s_dt.max().date()
                            d1 = st.date_input("From", value=dmin, key=f"from_{col_to_filter}")
                            d2 = st.date_input("To", value=dmax, key=f"to_{col_to_filter}")
                            if st.button("Add date filter"):
                                st.session_state.filters.append(("datetime", col_to_filter, d1, d2))
                        except Exception:
                            txt = st.text_input(f"Contains (text) for {col_to_filter}")
                            if txt and st.button("Add text filter"):
                                st.session_state.filters.append(("text", col_to_filter, txt))
                    else:
                        unique_vals = series.dropna().unique()
                        if len(unique_vals) <= 50:
                            chosen_vals = st.multiselect(f"Select values for {col_to_filter}", options=sorted(map(str, unique_vals)))
                            if chosen_vals and st.button("Add value filter"):
                                st.session_state.filters.append(("in", col_to_filter, chosen_vals))
                        else:
                            txt = st.text_input(f"Contains (case-insensitive) for {col_to_filter}")
                            if txt and st.button("Add text filter"):
                                st.session_state.filters.append(("text", col_to_filter, txt))

                # Show active filters with ability to clear
                if st.session_state.filters:
                    st.markdown("**Active filters:**")
                    for i, f in enumerate(st.session_state.filters):
                        st.write(f"{i+1}. {f}")
                    if st.button("Clear all filters"):
                        st.session_state.filters = []

                # Apply filters to DataFrame
                df = df_full.copy()
                for f in st.session_state.filters:
                    typ = f[0]
                    if typ == "numeric":
                        _, col, lo, hi = f
                        df = df[df[col].between(lo, hi)]
                    elif typ == "datetime":
                        _, col, d1, d2 = f
                        col_dt = pd.to_datetime(df[col], errors="coerce")
                        df = df[col_dt.between(pd.to_datetime(d1), pd.to_datetime(d2))]
                    elif typ == "text":
                        _, col, txt = f
                        df = df[df[col].astype(str).str.lower().str.contains(txt.lower(), na=False)]
                    elif typ == "in":
                        _, col, vals = f
                        df = df[df[col].astype(str).isin(vals)]

                # Display
                display_df = df[chosen_cols] if chosen_cols else df
                st.write(f"Showing {len(display_df)} rows (from {len(df_full)} total)")
                st.dataframe(display_df.reset_index(drop=True))

    # ---------- CRUD Operations ----------
    if menu == "✏️ CRUD Operations":
        st.header("✏️ CRUD Operations")
        tables = list_tables()
        table = st.selectbox("Choose table", tables)
        schema = get_schema(table)
        cols = [col[1] for col in schema]
        pk_cols = [col[1] for col in schema if col[5] == 1]
        pk_col = pk_cols[0] if pk_cols else cols[0]

        op = st.radio("Operation", ["Create", "Read", "Update", "Delete"]) 

        if op == "Read":
            df = read_table(table, limit=500)
            st.dataframe(df)

        if op == "Create":
            st.subheader("Create new record")
            new = {}
            for cid, name, ctype, notnull, dflt, pk in schema:
                val = st.text_input(f"{name} ({ctype})", key=f"create_{name}")
                if val != "":
                    new[name] = val
            if st.button("Insert"):
                try:
                    insert_row(table, new)
                    st.success("Inserted")
                except Exception as e:
                    st.error(f"Insert failed: {e}")

        if op == "Update":
            st.subheader("Update record")
            pk_val = st.text_input(f"Primary key ({pk_col}) value to update")
            if pk_val:
                # fetch row
                row = run_sql(f"SELECT * FROM {table} WHERE {pk_col} = '{pk_val}' LIMIT 1;")
                if row.empty:
                    st.warning("Row not found")
                else:
                    updates = {}
                    for c in cols:
                        newv = st.text_input(f"{c}", value=str(row.iloc[0][c]), key=f"upd_{c}")
                        updates[c] = newv
                    if st.button("Apply Update"):
                        try:
                            update_row(table, pk_col, pk_val, updates)
                            st.success("Updated")
                        except Exception as e:
                            st.error(f"Update failed: {e}")

        if op == "Delete":
            st.subheader("Delete record")
            pk_val = st.text_input(f"Primary key ({pk_col}) value to delete")
            if st.button("Delete") and pk_val:
                try:
                    delete_row(table, pk_col, pk_val)
                    st.success("Deleted")
                except Exception as e:
                    st.error(f"Delete failed: {e}")

    # ---------- Credit / Debit Simulation ----------
    if menu == "💰 Credit / Debit Simulation":
        st.header("💰 Credit / Debit Simulation")
        st.markdown("Enter a customer ID to view their account balance and perform deposit/withdrawal.")
        cust = st.text_input("Customer ID (e.g. C0001)")
        min_balance = 1000.0
        if cust:
            # find account
            df_acc = run_sql(f"SELECT * FROM accounts WHERE customer_id = '{cust}' LIMIT 1;")
            if df_acc.empty:
                st.warning("No account found for that customer")
            else:
                balance = float(df_acc.iloc[0]['account_balance'])
                st.metric("Current Balance", f"₹{balance:,.2f}")
                action = st.radio("Action", ["Deposit", "Withdraw"])
                amt = st.number_input("Amount (₹)", min_value=1.0, value=1000.0)
                if st.button("Execute"):
                    if action == "Withdraw" and (balance - amt) < min_balance:
                        st.error(f"Withdrawal would violate minimum balance ₹{min_balance:.0f}")
                    else:
                        new_bal = balance + amt if action == "Deposit" else balance - amt
                        # update accounts table
                        update_row("accounts", "customer_id", cust, {"account_balance": new_bal})
                        # insert transaction record
                        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        conn = get_conn()
                        txn_id = f"TXN_{int(datetime.datetime.now().timestamp())}"
                        conn.execute("INSERT INTO transactions (txn_id, customer_id, txn_type, amount, txn_time, status) VALUES (?,?,?,?,?,?);",
                                     (txn_id, cust, action.lower(), amt, ts, 'success'))
                        conn.commit()
                        st.success(f"{action} successful — new balance: ₹{new_bal:,.2f}")

    # ---------- Analytical Insights ----------
    if menu == "🧠 Analytical Insights":
        st.header("🧠 Analytical Insights")

        insights = {
            "Q1: How many customers exist per city, and what is their average account balance?": (
                """SELECT c.city, COUNT(DISTINCT c.customer_id) AS total_customers,
                Round(AVG(a.account_balance),2) AS avg_balance
                From customers c 
                JOIN accounts a ON c.customer_id=a.customer_id 
                GROUP BY c.city ORDER BY avg_balance DESC LIMIT 10;"""
            ),
            "Q2: Which account type (Savings, Current, Loan, etc.) holds the highest total balance?": (
                """SELECT c.account_type, SUM(a.account_balance) AS total_balance
                FROM customers c JOIN accounts a ON c.customer_id=a.customer_id 
                GROUP BY account_type ORDER BY total_balance DESC;"""
            ),
            "Q3: Who are the top 10 customers by total account balance across all account types?": (
                """SELECT c.customer_id, c.name, SUM(a.account_balance) AS total_balance
                from customers c JOIN accounts a ON c.customer_id=a.customer_id
                GROUP BY c.customer_id, c.name ORDER BY total_balance DESC LIMIT 10;"""
            ),
            "Q4: Which customers opened accounts in 2023 with a balance above ₹1,00,000?": (
               """SELECT c.customer_id, c.name, c.join_date , a.account_balance
               From customers c JOIN accounts a ON c.customer_id=a.customer_id
               WHERE strftime('%Y' , c.join_date)='2023' AND a.account_balance>100000;"""
            ),
            "Q5: What is the total transaction volume (sum of amounts) by transaction type?": (
                """SELECT txn_type, SUM(amount) AS total_amount
                FROM transactions GROUP BY txn_type ORDER BY total_amount DESC;"""
            ),
            "Q6: Which accounts have more than 3 failed transactions in a single month?": (
               """SELECT customer_id, COUNT(*) AS failed_count, strftime('%Y-%m', txn_time) AS month
               FROM transactions WHERE lower(trim(status)) = 'failed' 
               GROUP BY customer_id, month HAVING failed_count > 3;"""
            ),
            "Q7: Which are the top 5 branches by total transaction volume in the last 6 months?": (
                """SELECT a.Branch_Name, SUM(t.amount) AS total_volume 
                FROM branches t JOIN accounts a ON t.customer_id=a.customer_id
                GROUP BY a.Branch_Name ORDER BY total_volume DESC LIMIT 5;"""
            ),
            "Q8: Which accounts have 5 or more high-value transactions above ₹2,00,000?": (
              """SELECT customer_id, COUNT(*) AS high_value_count 
              FROM transactions WHERE amount >= 200000 
              GROUP BY customer_id HAVING high_value_count >= 5;"""
            ),
            "Q9: What is the average loan amount and interest rate by loan type (Personal, Auto, Home, etc.)?": (
               """SELECT loan_type, ROUND(AVG(loan_amount),2) AS avg_loan,
               ROUND(AVG(interest_rate),2) AS avg_rate 
               FROM loans GROUP BY loan_type; """
            ),
            "Q10: Which customers currently hold more than one active or approved loan?": (
                """SELECT customer_id,count(*) AS active_loans
                FROM loans WHERE loan_status IN ('Approved','Active')
                GROUP BY customer_id HAVING active_loans>1;"""
            ),
            "Q11: Who are the top 5 customers with the highest outstanding (non-closed) loan amounts?": (
                """SELECT customer_id, SUM(loan_amount) AS total_loan
                FROM loans WHERE loan_status!='Closed'
                GROUP BY customer_id ORDER BY total_loan DESC LIMIT 5;"""
            ),
            "Q12: Which branch holds the highest total account balance?": (
                 """SELECT branch, SUM(account_balance) AS total_balance
                 FROM accounts GROUP BY branch ORDER BY total_balance DESC LIMIT 1;"""
            ),
            "Q13: What is the branch performance summary showing total customers, total loans, and transaction volume?": (
               """SELECT b.branch_name,
               COUNT(DISTINCT a.customer_id) AS total_customers,
               COUNT(DISTINCT l.loan_id) AS total_loans,
               ROUND(SUM(a.account_balance),2) AS total_balance
               FROM branches b
               LEFT JOIN accounts a on b.branch_name=a.branch
               LEFT JOIN loans l ON a.customer_id=l.customer_id
               GROUP BY b.branch_name
               ORDER BY total_balance DESC LIMIT 10;"""
            ),
            "Q14: Which issue categories have the longest average resolution time?": (
                """SELECT issue_category,
                ROUND(AVG(julianday(Date_Closed)-julianday(Date_Opened)),2) AS avg_days,
                COUNT(*) AS total_tickets
                FROM support_tickets
                WHERE Date_Closed!=''
                GROUP BY issue_category ORDER BY avg_days DESC LIMIT 10;"""
            ),
            "Q15: Which support agents have resolved the most critical tickets with high customer ratings (≥4)?": (
                 """SELECT Support_Agent, COUNT(*) AS resolved_tickets
                 FROM support_tickets
                 WHERE priority='Critical' AND Customer_Rating>=4
                 GROUP BY Support_Agent ORDER BY resolved_tickets DESC LIMIT 5;"""
            ),
        }

        choice = st.selectbox("Choose an insight", list(insights.keys()))
        sql = insights[choice]
        st.code(sql)
        if st.button("Run Query"):
            df = run_sql(sql)
            st.dataframe(df)

    # ---------- About Creator ----------
    if menu == "👩‍💻 About Creator":
        st.header("👩‍💻 About Creator")
        st.markdown("**Name:** Shubham Rathore")
        st.markdown("**Expertise:** Data analysis, Python, SQL, Streamlit")
        st.markdown("**Contact:** shubhamrathore850@gmail.com")
        # Do not attempt to render a CSV as image; placeholder only
        st.write("Project files are in /mnt/data/")

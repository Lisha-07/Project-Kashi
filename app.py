
from flask import Flask, request, render_template_string
import mysql.connector
from datetime import date
import secrets
from decimal import Decimal

app = Flask(__name__)


# Connect to MySQL
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Zxcvbnm_07",
        database="kashi_bank"
    )


@app.route("/", methods=["GET", "POST"])
def home():
    message = ""
    message_type = ""

    # Process submitted forms
    if request.method == "POST":
        connection = None
        cursor = None

        try:
            action = request.form.get("action")
            connection = get_db_connection()
            cursor = connection.cursor()

            # 1. Register customer
            if action == "register_customer":
                first = request.form["first_name"].strip()
                last = request.form["last_name"].strip()

                if not first or not last:
                    raise ValueError("First and last names are required.")

                cursor.execute("""
                    INSERT INTO CUSTOMER
                    (FirstName, LastName, Mobile, Email, Address,
                     City, RegistrationDate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    first, last,
                    request.form.get("mobile", "").strip() or None,
                    request.form.get("email", "").strip() or None,
                    request.form.get("address", "").strip() or None,
                    request.form.get("city", "").strip() or None,
                    date.today()
                ))

                connection.commit()
                message = f"Customer registered! ID: {cursor.lastrowid}"
                message_type = "success"

            # 2. Create bank account
            elif action == "create_account":
                customer_id = int(request.form["customer_id"])
                branch_id = int(request.form["branch_id"])
                account_type = request.form["account_type"]

                if account_type not in ("Savings", "Current"):
                    raise ValueError("Select a valid account type.")

                cursor.execute(
                    "SELECT CustomerID FROM CUSTOMER WHERE CustomerID=%s",
                    (customer_id,)
                )
                if cursor.fetchone() is None:
                    raise ValueError("Customer ID does not exist.")

                cursor.execute(
                    "SELECT BranchID FROM BRANCH WHERE BranchID=%s",
                    (branch_id,)
                )
                if cursor.fetchone() is None:
                    raise ValueError("Branch ID does not exist.")

                account_number = secrets.token_hex(6).upper()

                cursor.execute("""
                    INSERT INTO ACCOUNT
                    (AccountNumber, AccountType, OpeningDate,
                     Balance, Status, BranchID)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    account_number, account_type,
                    date.today(), 0.00, "Active", branch_id
                ))

                account_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO ACCOUNT_HOLDER
                    (CustomerID, AccountID, HolderSince, HolderType)
                    VALUES (%s, %s, %s, %s)
                """, (customer_id, account_id, date.today(), "Primary"))

                connection.commit()
                message = (
                    f"Account created! ID: {account_id} | "
                    f"Number: {account_number}"
                )
                message_type = "success"

            # 3. Deposit or withdraw money
            elif action == "transaction":
                account_id = int(request.form["account_id"])
                amount = Decimal(request.form["amount"])
                transaction_type = request.form["transaction_type"]
                description = request.form.get("description", "").strip()

                if transaction_type not in ("Deposit", "Withdrawal"):
                    raise ValueError("Select Deposit or Withdrawal.")

                if not amount.is_finite() or amount <= 0:
                    raise ValueError("Enter an amount greater than zero.")

                if amount.as_tuple().exponent < -2:
                    raise ValueError("Use a maximum of two decimal places.")

                cursor.execute("""
                    SELECT Balance, Status
                    FROM ACCOUNT
                    WHERE AccountID = %s
                    FOR UPDATE
                """, (account_id,))

                account = cursor.fetchone()

                if account is None:
                    raise ValueError("Account ID does not exist.")

                balance = Decimal(str(account[0]))

                if account[1] != "Active":
                    raise ValueError("This account is not active.")

                if transaction_type == "Withdrawal" and amount > balance:
                    raise ValueError("Insufficient balance!")

                if transaction_type == "Deposit":
                    new_balance = balance + amount
                else:
                    new_balance = balance - amount

                if new_balance > Decimal("9999999999.99"):
                    raise ValueError("The resulting balance is too large.")

                cursor.execute("""
                    UPDATE ACCOUNT
                    SET Balance = %s
                    WHERE AccountID = %s
                """, (new_balance, account_id))

                cursor.execute("""
                    INSERT INTO `TRANSACTION`
                    (AccountID, TransactionType, Amount,
                     Description, TransactionStatus)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    account_id, transaction_type, amount,
                    description or transaction_type, "SUCCESS"
                ))

                connection.commit()

                message = (
                    f"{transaction_type} successful! "
                    f"New balance: ₹{new_balance:.2f}"
                )
                message_type = "success"

            else:
                raise ValueError("Invalid action.")

        except Exception as error:
            if connection is not None:
                connection.rollback()

            message = f"Error: {error}"
            message_type = "error"

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None and connection.is_connected():
                connection.close()

    # Load information for the website
    customers = []
    accounts = []
    transactions = []

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT CustomerID, FirstName, LastName, Mobile,
                   Email, City, RegistrationDate
            FROM CUSTOMER
            ORDER BY CustomerID DESC
        """)
        customers = cursor.fetchall()

        cursor.execute("""
            SELECT A.AccountID, A.AccountNumber, A.AccountType,
                   A.Balance, A.Status, B.BranchName,
                   C.FirstName, C.LastName
            FROM ACCOUNT A
            JOIN ACCOUNT_HOLDER AH ON A.AccountID = AH.AccountID
            JOIN CUSTOMER C ON AH.CustomerID = C.CustomerID
            LEFT JOIN BRANCH B ON A.BranchID = B.BranchID
            ORDER BY A.AccountID DESC
        """)
        accounts = cursor.fetchall()

        cursor.execute("""
            SELECT T.TransactionID, T.AccountID,
                   T.TransactionType, T.Amount,
                   T.TransactionDate, T.Description,
                   T.TransactionStatus, A.AccountNumber
            FROM `TRANSACTION` T
            JOIN ACCOUNT A ON T.AccountID = A.AccountID
            ORDER BY T.TransactionID DESC
            LIMIT 50
        """)
        transactions = cursor.fetchall()

    except Exception as error:
        if not message:
            message = f"Could not load data: {error}"
            message_type = "error"

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    # Website layout
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Project KASHI</title>

        <style>
            * { box-sizing: border-box; }

            body {
                font-family: Arial, sans-serif;
                background: #eef2f7;
                color: #222;
                margin: 0;
                padding: 20px 12px;
            }

            header {
                max-width: 1100px;
                margin: auto;
                padding: 24px;
                text-align: center;
                background: #163a70;
                color: white;
                border-radius: 12px;
            }

            .forms {
                max-width: 1100px;
                margin: 22px auto;
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(270px, 1fr));
                gap: 18px;
            }

            .card, .section {
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 3px 12px #d5dce5;
                min-width: 0;
            }

            h2 { color: #163a70; font-size: 20px; }

            label {
                display: block;
                margin-top: 12px;
                font-weight: bold;
                font-size: 14px;
            }

            input, select {
                width: 100%;
                padding: 10px;
                margin-top: 5px;
                border: 1px solid #ccc;
                border-radius: 5px;
            }

            button {
                width: 100%;
                padding: 12px;
                margin-top: 18px;
                background: #163a70;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
            }

            button:hover { background: #24549a; }

            .section {
                max-width: 1100px;
                margin: 22px auto;
            }

            .message {
                max-width: 1100px;
                margin: 18px auto;
                padding: 14px;
                border-radius: 7px;
                overflow-wrap: anywhere;
            }

            .success { background: #e2f5e8; color: #17632d; }
            .error { background: #fde8e8; color: #9b1c1c; }

            .note { font-size: 13px; color: #666; }

            .table-container { overflow-x: auto; }

            table {
                width: 100%;
                min-width: 650px;
                border-collapse: collapse;
                margin-top: 12px;
            }

            th, td {
                text-align: left;
                padding: 10px;
                border-bottom: 1px solid #ddd;
                font-size: 13px;
            }

            th { background: #163a70; color: white; }
            tr:hover { background: #f2f5fa; }
        </style>
    </head>

    <body>
        <header>
            <h1>PROJECT KASHI</h1>
            <p>Banking Management System</p>
            <p>Customer, Account and Transaction Management</p>
        </header>

        {% if message %}
        <div class="message {{ message_type }}">{{ message }}</div>
        {% endif %}

        <div class="forms">

            <section class="card">
                <h2>Register Customer</h2>
                <form method="POST">
                    <input type="hidden" name="action"
                           value="register_customer">

                    <label>First Name *</label>
                    <input name="first_name" required>

                    <label>Last Name *</label>
                    <input name="last_name" required>

                    <label>Mobile</label>
                    <input name="mobile" type="tel">

                    <label>Email</label>
                    <input name="email" type="email">

                    <label>Address</label>
                    <input name="address">

                    <label>City</label>
                    <input name="city">

                    <button type="submit">Register Customer</button>
                </form>
            </section>

            <section class="card">
                <h2>Create Bank Account</h2>
                <form method="POST">
                    <input type="hidden" name="action"
                           value="create_account">

                    <label>Customer ID *</label>
                    <input name="customer_id" type="number" min="1" required>

                    <label>Account Type *</label>
                    <select name="account_type" required>
                        <option value="">Select type</option>
                        <option value="Savings">Savings</option>
                        <option value="Current">Current</option>
                    </select>

                    <label>Branch ID *</label>
                    <input name="branch_id" type="number" min="1" required>

                    <button type="submit">Create Account</button>
                </form>
            </section>

            <section class="card">
                <h2>Deposit / Withdraw</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="transaction">

                    <label>Account ID *</label>
                    <input name="account_id" type="number" min="1" required>

                    <label>Transaction Type *</label>
                    <select name="transaction_type" required>
                        <option value="Deposit">Deposit</option>
                        <option value="Withdrawal">Withdrawal</option>
                    </select>

                    <label>Amount (₹) *</label>
                    <input name="amount" type="number"
                           min="0.01" step="0.01" required>

                    <label>Description</label>
                    <input name="description"
                           placeholder="Optional description">

                    <button type="submit">Process Transaction</button>
                </form>

                <p class="note">
                    Use an existing Account ID. Withdrawals cannot exceed
                    the available balance.
                </p>
            </section>

        </div>

        <section class="section">
            <h2>Registered Customers</h2>
            <div class="table-container">
                <table>
                    <tr>
                        <th>ID</th><th>Name</th><th>Mobile</th>
                        <th>Email</th><th>City</th>
                    </tr>
                    {% for c in customers %}
                    <tr>
                        <td>{{ c.CustomerID }}</td>
                        <td>{{ c.FirstName }} {{ c.LastName }}</td>
                        <td>{{ c.Mobile or "-" }}</td>
                        <td>{{ c.Email or "-" }}</td>
                        <td>{{ c.City or "-" }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </section>

        <section class="section">
            <h2>Bank Accounts</h2>
            <div class="table-container">
                <table>
                    <tr>
                        <th>Account ID</th><th>Account Number</th>
                        <th>Customer</th><th>Type</th>
                        <th>Balance</th><th>Status</th><th>Branch</th>
                    </tr>
                    {% for a in accounts %}
                    <tr>
                        <td>{{ a.AccountID }}</td>
                        <td>{{ a.AccountNumber }}</td>
                        <td>{{ a.FirstName }} {{ a.LastName }}</td>
                        <td>{{ a.AccountType }}</td>
                        <td>₹{{ "%.2f"|format(a.Balance) }}</td>
                        <td>{{ a.Status }}</td>
                        <td>{{ a.BranchName or "-" }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </section>

        <section class="section">
            <h2>Recent Transactions</h2>
            <p class="note">Showing the latest 50 transactions.</p>
            <div class="table-container">
                <table>
                    <tr>
                        <th>ID</th><th>Account</th><th>Type</th>
                        <th>Amount</th><th>Date</th>
                        <th>Description</th><th>Status</th>
                    </tr>
                    {% for t in transactions %}
                    <tr>
                        <td>{{ t.TransactionID }}</td>
                        <td>{{ t.AccountNumber }}</td>
                        <td>{{ t.TransactionType }}</td>
                        <td>₹{{ "%.2f"|format(t.Amount) }}</td>
                        <td>{{ t.TransactionDate }}</td>
                        <td>{{ t.Description or "-" }}</td>
                        <td>{{ t.TransactionStatus }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </section>
    </body>
    </html>
    """, message=message, message_type=message_type,
       customers=customers, accounts=accounts,
       transactions=transactions)


if __name__ == "__main__":
    app.run(debug=True)

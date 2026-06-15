"""
ANOMALY DETECTION AGENT
Detects business-level anomalies in the transformed data and produces
a concise risk narrative using the Groq LLM.
Does not modify data; findings are advisory only.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()


def detect_anomalies(transformed: dict) -> dict:
    print("\n========== ANOMALY DETECTION AGENT ==========")
    findings: dict = {}

    # --- Accounts: negative balances ---
    accounts_df = transformed.get("accounts")
    if accounts_df is not None and not accounts_df.empty:
        if "AccountBalance" in accounts_df.columns:
            n = int((accounts_df["AccountBalance"] < 0).sum())
            if n:
                findings["accounts"] = [
                    f"{n:,} accounts with negative balance"]

    # --- Transactions: unusually large amounts ---
    tx_df = transformed.get("transactions")
    if tx_df is not None and not tx_df.empty:
        if "Amount" in tx_df.columns:
            threshold = 10_000_000
            n = int((tx_df["Amount"] > threshold).sum())
            if n:
                findings["transactions"] = [
                    f"{n:,} transactions exceeding {threshold:,}"
                ]

    # --- Loans: defaulted status ---
    loans_df = transformed.get("loans")
    if loans_df is not None and not loans_df.empty:
        if "LoanStatus" in loans_df.columns:
            n = int(
                (loans_df["LoanStatus"].astype(
                    str).str.strip().str.lower() == "defaulted").sum()
            )
            if n:
                findings["loans"] = [f"{n:,} defaulted loans"]

    # --- Customers: inactive accounts ---
    customers_df = transformed.get("customers")
    if customers_df is not None and not customers_df.empty:
        if "CustomerStatus" in customers_df.columns:
            n = int(
                (customers_df["CustomerStatus"].astype(
                    str).str.strip().str.lower() == "inactive").sum()
            )
            if n:
                findings["customers"] = [f"{n:,} inactive customer records"]

    print(f"Found {len(findings)} anomaly type(s)")

    # --- LLM risk narrative (optional) ---
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key and groq_key not in ("", "gsk_your_key_here") and findings:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            payload = json.dumps(findings, indent=2)
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a banking risk analyst. "
                            "Produce a concise, structured risk assessment. "
                            "Use plain language. No markdown headers. Max 300 words."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"The following anomalies were detected during a core banking "
                            f"data migration:\n\n{payload}\n\n"
                            "Provide: (1) overall risk rating, (2) key risks, "
                            "(3) recommended actions."
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=400,
            )
            findings["ai_risk_narrative"] = response.choices[0].message.content
        except Exception as exc:
            findings["ai_risk_narrative"] = (
                f"LLM narrative unavailable: {str(exc)[:120]}"
            )

    return findings

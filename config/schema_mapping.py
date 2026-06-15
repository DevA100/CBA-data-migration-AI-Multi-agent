"""
SCHEMA MAPPING
Default column-level mapping from legacy source to target banking schema.
Users may supply their own JSON file; this module provides the fallback.
"""

import json


def get_default_mapping() -> dict:
    return {
        "batch_size": 50000,
        "parallel_threads": 4,
        "tables": {
            "branch": {
                "source_table": "branch",
                "target_table": "Branch",
                "columns": {
                    "branch_code": "BranchCode",
                    "branch_name": "BranchName",
                    "location":    "Location",
                },
            },
            "customers": {
                "source_table": "customers",
                "target_table": "Customers",
                "columns": {
                    "cust_id":      "CustomerId",
                    "full_name":    "CustomerName",
                    "gender":       "Gender",
                    "dob":          "DateOfBirth",
                    "phone_no":     "PhoneNumber",
                    "email_addr":   "EmailAddress",
                    "bvn_no":       "BVN",
                    "nat_id":       "NationalID",
                    "addr":         "Address",
                    "date_created": "CreatedAt",
                    "cust_status":  "CustomerStatus",
                },
            },
            "accounts": {
                "source_table": "accounts",
                "target_table": "Accounts",
                "columns": {
                    "acct_id":     "AccountId",
                    "cust_id":     "CustomerId",
                    "acct_num":    "AccountNumber",
                    "acct_type":   "AccountType",
                    "bal":         "AccountBalance",
                    "currency":    "Currency",
                    "branch_code": "BranchCode",
                    "open_date":   "OpeningDate",
                    "acct_status": "AccountStatus",
                },
            },
            "transactions": {
                "source_table": "transactions",
                "target_table": "Transactions",
                "columns": {
                    "trans_id":  "TransactionId",
                    "acct_num":  "AccountNumber",
                    "amt":       "Amount",
                    "txn_type":  "TransactionType",
                    "txn_date":  "TransactionDate",
                    "narration": "Narration",
                    "channel":   "TransactionChannel",
                },
            },
            "loans": {
                "source_table": "loans",
                "target_table": "Loans",
                "columns": {
                    "loan_id":       "LoanId",
                    "cust_id":       "CustomerId",
                    "loan_amt":      "LoanAmount",
                    "interest_rate": "InterestRate",
                    "loan_type":     "LoanType",
                    "approval_date": "ApprovalDate",
                    "loan_status":   "LoanStatus",
                },
            },
        },
        "insert_order": ["branch", "customers", "accounts", "loans", "transactions"],
    }


def validate_mapping(mapping: dict) -> bool:
    for key in ("tables", "insert_order"):
        if key not in mapping:
            raise ValueError(
                f"Schema mapping is missing required key: '{key}'")
    for table in mapping["insert_order"]:
        if table not in mapping["tables"]:
            raise ValueError(
                f"Table '{table}' listed in insert_order but not defined in tables"
            )
    return True


def load_mapping_from_file(path: str) -> dict:
    with open(path, "r") as fh:
        mapping = json.load(fh)
    validate_mapping(mapping)
    return mapping

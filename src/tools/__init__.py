from src.tools.budget_tool import query_department_budget, check_budget_sufficient, get_all_department_budgets
from src.tools.progress_tool import query_reimbursement_progress, query_reimbursements_by_date
from src.tools.compliance_tool import compliance_check, calculate_total_amount, get_expense_policy
from src.tools.ocr_tool import ocr_invoice, batch_ocr_invoices
from src.tools.pdf_tool import generate_reimbursement_pdf
from src.tools.email_tool import send_email, notify_approver
from src.tools.reimbursement_tool import create_reimbursement, submit_for_approval
from src.tools.approval_tool import approve_or_reject_reimbursement

ALL_TOOLS = [
    query_department_budget,
    check_budget_sufficient,
    get_all_department_budgets,
    query_reimbursement_progress,
    query_reimbursements_by_date,
    compliance_check,
    calculate_total_amount,
    get_expense_policy,
    ocr_invoice,
    batch_ocr_invoices,
    generate_reimbursement_pdf,
    send_email,
    notify_approver,
    create_reimbursement,
    submit_for_approval,
    approve_or_reject_reimbursement,
]
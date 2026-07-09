from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(32), unique=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(20), nullable=False, default='employee')  # employee / manager / admin
    name = Column(String(100), nullable=False)
    email = Column(String(100),nullable=False)
    department_id = Column(String(32), ForeignKey('department_budget.department_id'))
    created_at = Column(DateTime, default=datetime.now)


class DepartmentApprover(Base):
    __tablename__ = 'department_approvers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(String(32), ForeignKey('department_budget.department_id'), nullable=False)
    approval_level = Column(Integer, nullable=False)
    approver_id = Column(String(32), nullable=False)
    approver_name = Column(String(100), nullable=False)


class Reimbursements(Base):
    __tablename__ = 'reimbursements'

    id = Column(Integer, primary_key=True, autoincrement=True)
    reimbursement_no = Column(String(32), unique=True, nullable=False)
    source_reimbursement_no = Column(String(32), nullable=True)
    employee_id = Column(String(32), nullable=False)
    employee_name = Column(String(100), nullable=False)
    department_id = Column(String(32), ForeignKey('department_budget.department_id'))
    expense_type = Column(String(50), nullable=False)
    total_amount = Column(Float, nullable=False)
    description = Column(Text)
    status = Column(String(20), default='pending')
    need_special_approval = Column(Boolean, default=False)
    invoice_details = Column(Text, default=None)
    applicant_email = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    department = relationship('DepartmentBudget', back_populates='reimbursements')
    approval_records = relationship('ApprovalRecords', back_populates='reimbursement', cascade='all, delete-orphan')
    invoices = relationship('Invoice', back_populates='reimbursement')
    vouchers = relationship('Voucher', back_populates='reimbursement')


class Invoice(Base):
    __tablename__ = 'invoices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_code = Column(String(50))
    invoice_number = Column(String(50))
    invoice_type = Column(String(50))
    invoice_type_name = Column(String(50))
    amount = Column(Float, default=0.0)
    invoice_date = Column(String(20))
    seller_name = Column(String(200))
    seller_tax_id = Column(String(50))
    buyer_name = Column(String(200))
    buyer_tax_id = Column(String(50))
    confidence = Column(String(20))
    file_path = Column(String(500))
    uploaded_by = Column(String(32), ForeignKey('users.user_id'))
    reimbursement_id = Column(Integer, ForeignKey('reimbursements.id'), nullable=True)
    reimbursement_no = Column(String(32), nullable=True)
    is_valid = Column(Boolean, default=True)
    invalid_reason = Column(String(200))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    uploader = relationship('User')
    reimbursement = relationship('Reimbursements', back_populates='invoices')


class Voucher(Base):
    __tablename__ = 'vouchers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    voucher_type = Column(String(50), default="其他")
    amount = Column(Float, default=0.0)
    payment_date = Column(String(20))
    payee = Column(String(200))
    description = Column(Text)
    ocr_result = Column(Text)
    file_path = Column(String(500))
    uploaded_by = Column(String(32), ForeignKey('users.user_id'))
    reimbursement_id = Column(Integer, ForeignKey('reimbursements.id'), nullable=True)
    reimbursement_no = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    uploader = relationship('User')
    reimbursement = relationship('Reimbursements', back_populates='vouchers')


class DepartmentBudget(Base):
    __tablename__ = 'department_budget'

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(String(32), unique=True, nullable=False)
    department_name = Column(String(100), nullable=False)
    budget_amount = Column(Float, nullable=False)
    spent_amount = Column(Float, default=0.0)
    remaining_amount = Column(Float)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    reimbursements = relationship('Reimbursements', back_populates='department')


class ApprovalRecords(Base):
    __tablename__ = 'approval_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    reimbursement_id = Column(Integer, ForeignKey('reimbursements.id'))
    approver_id = Column(String(32), nullable=False)
    approver_name = Column(String(100), nullable=False)
    approval_level = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    comment = Column(Text)
    approved_at = Column(DateTime, default=datetime.now)

    reimbursement = relationship('Reimbursements', back_populates='approval_records')


class ChatHistory(Base):  # 新增对话历史表
    __tablename__ = 'chat_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(32), nullable=False, index=True)      # 用户ID
    role = Column(String(20), nullable=False)                     # user / assistant
    content = Column(Text, nullable=False)                        # 消息内容
    created_at = Column(DateTime, default=datetime.now, index=True)

    # 可选：关联报销单（如果对话中产生了报销单）
    reimbursement_id = Column(Integer, ForeignKey('reimbursements.id'), nullable=True)

    # 可选：会话ID（如果希望支持多会话）
    # session_id = Column(String(64), nullable=True, index=True)
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
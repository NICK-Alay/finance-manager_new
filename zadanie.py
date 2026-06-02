from datetime import date
from enum import Enum
from typing import List, Literal, Optional

import uvicorn

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    Date,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    func,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

DATABASE_URL = "sqlite:///./database.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class OperationType(str, Enum):
    income = "income"
    expense = "expense"


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(String(256), nullable=True)
    operations = relationship(
        "Operation",
        back_populates="category",
        cascade="all, delete-orphan",
    )


class Operation(Base):
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    date = Column(Date, nullable=False, index=True)
    type = Column(SAEnum(OperationType, native_enum=False), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    note = Column(String(256), nullable=True)

    category = relationship("Category", back_populates="operations")


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=256)


class CategoryRead(CategoryCreate):
    id: int

    class Config:
        orm_mode = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=256)


class OperationCreate(BaseModel):
    amount: float = Field(..., gt=0)
    date: date
    type: OperationType
    category_id: int
    note: Optional[str] = Field(None, max_length=256)


class OperationRead(OperationCreate):
    id: int
    category: CategoryRead

    class Config:
        orm_mode = True


class OperationUpdate(BaseModel):
    amount: Optional[float] = Field(None, gt=0)
    date: Optional[date]
    type: Optional[OperationType]
    category_id: Optional[int]
    note: Optional[str] = Field(None, max_length=256)


class BalanceRead(BaseModel):
    income: float
    expense: float
    balance: float


app = FastAPI(title="Personal Finance Management API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        default_categories = [
            ("Еда", "Продукты, кафе и питание"),
            ("Транспорт", "Проезд, такси, топливо"),
            ("Развлечения", "Кино, хобби, отдых"),
        ]
        for name, description in default_categories:
            existing = (
                db.query(Category)
                .filter(func.lower(Category.name) == name.lower())
                .first()
            )
            if not existing:
                db.add(Category(name=name, description=description))
        db.commit()


@app.post("/categories", response_model=CategoryRead)
def create_category(category: CategoryCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(Category)
        .filter(func.lower(Category.name) == category.name.lower())
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Категория с таким именем уже существует")
    db_category = Category(name=category.name, description=category.description)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


@app.get("/categories", response_model=List[CategoryRead])
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).order_by(Category.name).all()


@app.put("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    category_update: CategoryUpdate,
    db: Session = Depends(get_db),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    if category_update.name and category_update.name != category.name:
        duplicate = (
            db.query(Category)
            .filter(func.lower(Category.name) == category_update.name.lower())
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Категория с таким именем уже существует")
        category.name = category_update.name
    if category_update.description is not None:
        category.description = category_update.description
    db.commit()
    db.refresh(category)
    return category


@app.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    if category.operations:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить категорию, пока в ней есть операции",
        )
    db.delete(category)
    db.commit()
    return {"detail": "Категория удалена"}


@app.post("/operations", response_model=OperationRead)
def create_operation(operation: OperationCreate, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == operation.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    db_operation = Operation(
        amount=operation.amount,
        date=operation.date,
        type=operation.type,
        category_id=operation.category_id,
        note=operation.note,
    )
    db.add(db_operation)
    db.commit()
    db.refresh(db_operation)
    return db_operation


@app.get("/operations", response_model=List[OperationRead])
def list_operations(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    category_id: Optional[int] = Query(None),
    type: Optional[OperationType] = Query(None),
    sort_by: Literal["date", "amount", "type", "category"] = Query("date"),
    sort_order: Literal["asc", "desc"] = Query("asc"),
    db: Session = Depends(get_db),
):
    query = db.query(Operation).join(Operation.category)

    if date_from:
        query = query.filter(Operation.date >= date_from)
    if date_to:
        query = query.filter(Operation.date <= date_to)
    if category_id:
        query = query.filter(Operation.category_id == category_id)
    if type:
        query = query.filter(Operation.type == type)

    sort_columns = {
        "date": Operation.date,
        "amount": Operation.amount,
        "type": Operation.type,
        "category": Category.name,
    }
    order_column = sort_columns[sort_by]
    if sort_order == "desc":
        order_column = order_column.desc()
    query = query.order_by(order_column)

    return query.all()


@app.get("/operations/{operation_id}", response_model=OperationRead)
def get_operation(operation_id: int, db: Session = Depends(get_db)):
    operation = db.query(Operation).filter(Operation.id == operation_id).first()
    if not operation:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    return operation


@app.put("/operations/{operation_id}", response_model=OperationRead)
def update_operation(
    operation_id: int,
    operation_update: OperationUpdate,
    db: Session = Depends(get_db),
):
    operation = db.query(Operation).filter(Operation.id == operation_id).first()
    if not operation:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    if operation_update.category_id is not None:
        category = db.query(Category).filter(Category.id == operation_update.category_id).first()
        if not category:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        operation.category_id = operation_update.category_id
    if operation_update.amount is not None:
        operation.amount = operation_update.amount
    if operation_update.date is not None:
        operation.date = operation_update.date
    if operation_update.type is not None:
        operation.type = operation_update.type
    if operation_update.note is not None:
        operation.note = operation_update.note

    db.commit()
    db.refresh(operation)
    return operation


@app.delete("/operations/{operation_id}")
def delete_operation(operation_id: int, db: Session = Depends(get_db)):
    operation = db.query(Operation).filter(Operation.id == operation_id).first()
    if not operation:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    db.delete(operation)
    db.commit()
    return {"detail": "Операция удалена"}


@app.get("/balance", response_model=BalanceRead)
def get_balance(db: Session = Depends(get_db)):
    income_total = (
        db.query(func.coalesce(func.sum(Operation.amount), 0.0))
        .filter(Operation.type == OperationType.income)
        .scalar()
    )
    expense_total = (
        db.query(func.coalesce(func.sum(Operation.amount), 0.0))
        .filter(Operation.type == OperationType.expense)
        .scalar()
    )
    return BalanceRead(
        income=round(income_total or 0.0, 2),
        expense=round(expense_total or 0.0, 2),
        balance=round((income_total or 0.0) - (expense_total or 0.0), 2),
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

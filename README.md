# Banking Data Migration System

A production-grade, multi-agent ETL pipeline for migrating core banking data from legacy PostgreSQL databases to modern schemas. Built with LangChain, CrewAI, LangGraph, and Streamlit.

## Overview

This system orchestrates multiple AI agents to plan, validate, transform, and load banking data while maintaining referential integrity across 1M+ records. It includes automated data quality scanning, anomaly detection, and comprehensive audit logging.

**Key Features:**

- Multi-agent collaboration (LangChain planning, CrewAI coordination, LangGraph state tracking)
- FK chain tracking to prevent orphaned records
- Batch processing with row-by-row fallback
- Data quality scanning and auto-repair
- Anomaly detection with AI risk assessment
- Real-time progress monitoring via Streamlit UI
- Complete audit trail via mismatch logger

## Architecture

Data Flow:
Source DB → Extraction Agent → Transformation Agent → Validation Agent → Load Agent → Target DB
↓
Anomaly Detection Agent
↓
AI Risk Assessment (Groq LLM)

AI Orchestration:
LangChain Agent → Migration Planning (batch size, threads, time estimation)
CrewAI Agents → Extraction Expert, Validation Specialist, Risk Assessor
LangGraph → State machine tracking extract/transform/load phases

```bash
# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your database credentials

# Run
streamlit run app.py
```

from setuptools import setup, find_packages

setup(
    name="orca",
    version="2.0.0",
    description="Open-source Rules Compliance Auditor - Context-aware, LLM-powered compliance auditing for C/C++",
    long_description="ORCA is a multi-agent compliance auditing framework for C/C++ codebases featuring "
                     "context-aware analysis (header resolution, constraint generation), 7 compliance "
                     "agents, 7 static analyzers, and a human-in-the-loop fixer workflow.",
    author="ORCA Team",
    python_requires=">=3.9",
    packages=find_packages(),
    install_requires=[
        "pyyaml>=6.0",
        "openpyxl>=3.1.0",
        "psycopg2-binary>=2.9.0",
    ],
    extras_require={
        "ui": ["streamlit>=1.30.0"],
        "llm": ["anthropic>=0.15.0", "openai>=1.0.0"],
        "dev": ["pytest>=7.0", "pytest-cov>=4.0"],
        "pg": ["psycopg2>=2.9.0"],
        "all": ["streamlit>=1.30.0", "anthropic>=0.15.0", "openai>=1.0.0", "psycopg2>=2.9.0"],
    },
    entry_points={
        "console_scripts": ["orca=main:main"],
    },
)

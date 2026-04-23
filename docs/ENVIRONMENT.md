# Python Environment Standard

## Requirement
All Python-related tasks for the `mezamashi-lingo` project **must** utilize the local virtual environment. This ensures dependency isolation and consistency.

## Virtual Environment Location
The virtual environment is located at:
`./venv`

## Usage Instructions

### 1. Installing Packages
Always use the pip binary inside the venv:
```bash
./venv/bin/pip install <package_name>
```

### 2. Running the Application
Always use the python binary inside the venv:
```bash
./venv/bin/python main.py
```

### 3. Updating Requirements
After adding new dependencies, update the `requirements.txt` file:
```bash
./venv/bin/pip freeze > requirements.txt
```

## Rationale
Using the local `venv` prevents "it works on my machine" issues by ensuring every contributor and automation script uses the exact same set of dependencies.

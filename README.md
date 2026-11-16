# Internal AI Team Agent

## How to Run the Application

Before running the application, make sure you have activated your virtual environment and installed the required dependencies.

### 1. Initialize the Database

Run the following command first to initialize the database and insert the seed data:

```bash
python -m app.db.seed
```

### 2. Run the Streamlit Application

After the database initialization is complete, start the application using:

```bash
python -m streamlit run app/main.py
```

The application will open in your default browser.

**Important:** Always run the database initialization command before starting the application, especially when setting up the project for the first time.

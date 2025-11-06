# N-Port Fund Viewer

This is a website to explore how financial data can be accessed and visualized using public SEC filings.  
You can enter any fund’s CIK number, and the app will get the most recent N-PORT filing to display the fund’s holdings in a database table.

## Run it locally
1. Clone the repo  
   ```bash
   git clone https://github.com/Nishajakkinpali/NPort.git
   cd NPort
2. Create Virtual Enviornment
   ```bash
   python3 -m venv env
   source env/bin/activate
4. Install dependencies
   ```bash
   pip install -r requirements.txt
6. Run the FastAPI server
   ```bash
   uvicorn backend:app --reload
```bash
Go to http://127.0.0.1:8000/

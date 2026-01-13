# Desktop Build Instructions

## Quick Start

1. **Install Python 3.8+** (if not already installed)
   - Download from https://www.python.org/
   - **Important:** Check "Add Python to PATH" during installation

2. **Run Setup** (first time only)
   - Double-click `setup_desktop.bat`
   - This will install all required packages

3. **Launch the App**
   - Double-click `launch_app.bat`
   - The app will open in your default web browser
   - To stop the app, close the command window or press Ctrl+C

## Manual Setup (Alternative)

If the batch files don't work, you can set up manually:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
cd scripts
streamlit run app.py
```

## Creating a Standalone Executable (Advanced)

To create a true standalone .exe file (optional, requires PyInstaller):

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```

2. Create executable:
   ```bash
   pyinstaller --onefile --windowed --name "MutagenesisApp" --add-data "scripts;scripts" --add-data "data;data" --add-data "pdb;pdb" launch_app.py
   ```

Note: Creating a standalone executable is complex for Streamlit apps. The batch file launcher is the recommended approach.

## Troubleshooting

- **"Python is not recognized"**: Make sure Python is installed and added to PATH
- **"Module not found"**: Run `setup_desktop.bat` again
- **Port already in use**: Close other Streamlit apps or change the port:
  ```bash
  streamlit run app.py --server.port 8502
  ```

## Features

- ✅ Upload your own PDB files
- ✅ View protein 3D structures with mutation visualization
- ✅ Smooth animation through positions
- ✅ Protein information from RCSB PDB
- ✅ Interactive charts and visualizations


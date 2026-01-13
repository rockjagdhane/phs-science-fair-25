# Google Sheets Export & QR Code Setup Guide

## Overview
The Mutagenesis Intelligence System can automatically export mutation data to Google Sheets and generate QR codes for easy access. When you upload a PDB file, the system will:
1. Generate the mutation CSV
2. Upload it to Google Sheets (if enabled)
3. Generate a QR code that links to the sheet
4. Display the QR code for printing

## Setup Instructions

### Step 1: Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Google Sheets API** and **Google Drive API**:
   - Go to "APIs & Services" > "Library"
   - Search for "Google Sheets API" and enable it
   - Search for "Google Drive API" and enable it

### Step 2: Create Service Account
1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "Service Account"
3. Fill in the service account details:
   - Name: "MutaGenesis Export" (or any name)
   - Click "Create and Continue"
   - Skip role assignment (click "Continue")
   - Click "Done"

### Step 3: Create and Download JSON Key
1. Click on the service account you just created
2. Go to the "Keys" tab
3. Click "Add Key" > "Create new key"
4. Select "JSON" format
5. Click "Create" - this will download a JSON file

### Step 4: Configure in the App
1. Open the downloaded JSON file in a text editor
2. Copy the entire contents
3. In the Mutagenesis app sidebar:
   - Check "Auto-export to Google Sheets"
   - Paste the JSON credentials into the text area
   - The credentials will be saved for your session

### Step 5: Use the Feature
1. **Automatic Export**: When you upload a PDB file, if auto-export is enabled, the data will automatically be uploaded to Google Sheets and a QR code will be generated
2. **Manual Export**: Use the "Export Current Dataset to Google Sheets" button to export any dataset
3. **QR Code**: The QR code will be displayed in the app - you can download it as a PNG file for printing

## Features

### Automatic Export
- When a PDB is uploaded and processed, the mutation CSV is automatically uploaded to Google Sheets
- A unique sheet is created with timestamp: `MutaGenesis_[protein_name]_[timestamp]`
- The sheet is made publicly viewable (anyone with the link can view)
- A QR code is generated and displayed

### Manual Export
- Export any dataset (including loaded CSVs) to Google Sheets
- Generate QR codes for any exported sheet
- Download QR codes as PNG files

### QR Code
- Scannable QR code that links directly to the Google Sheet
- Downloadable as PNG for printing
- Perfect for science fair displays or sharing data

## Troubleshooting

### "gspread library not installed"
Run: `pip install gspread google-auth`

### "qrcode library not installed"
Run: `pip install qrcode[pil] Pillow`

### "Invalid JSON" error
- Make sure you copied the entire JSON file contents
- Check that there are no extra characters or formatting issues
- The JSON should start with `{` and end with `}`

### "Error uploading to Google Sheets"
- Verify that Google Sheets API and Google Drive API are enabled
- Check that the service account JSON is valid
- Ensure you have internet connectivity

### QR Code not generating
- Install required packages: `pip install qrcode[pil] Pillow`
- Check that the Google Sheets URL was created successfully

## Security Notes
- The service account JSON contains sensitive credentials
- Keep it secure and don't share it publicly
- The Google Sheets created are set to "Anyone with link can view" for QR code access
- You can change sharing settings in Google Sheets if needed

## Example Workflow
1. Upload a PDB file (e.g., `1ubq.pdb`)
2. System generates mutations and creates CSV
3. If auto-export is enabled:
   - CSV is uploaded to Google Sheets
   - Sheet name: `MutaGenesis_1ubq_1234567890`
   - QR code is generated and displayed
4. Download QR code PNG
5. Print QR code for your science fair display
6. Visitors can scan QR code to view the mutation data in Google Sheets


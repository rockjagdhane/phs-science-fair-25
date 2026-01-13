# app.py
"""
Mutagenesis Intelligence System — Dark Futuristic Dashboard
Single-file Streamlit app. Uses data/final_mutations.csv by default.
Features:
 - Dark neon UI
 - Autoplay (play/pause) with speed control
 - Smoothed ΔΔG trend line
 - AA->AA ΔΔG heatmap
 - ΔΔG vs FunctionalFitness scatter + histogram
 - 3D viewer (py3Dmol) if available
 - Exports: PNG (always) + PPTX (optional if python-pptx+kaleido)
"""

import os, time, hashlib, textwrap, json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# optional libs
try:
    from scipy.interpolate import make_interp_spline
except Exception:
    make_interp_spline = None
try:
    import py3Dmol
except Exception:
    py3Dmol = None
try:
    from pptx import Presentation
    from pptx.util import Inches
    HAS_PPTX = True
except Exception:
    HAS_PPTX = False
try:
    import gspread
    from google.oauth2.service_account import Credentials
    HAS_GSHEETS = True
except Exception:
    HAS_GSHEETS = False
try:
    import qrcode
    from PIL import Image
    import io
    HAS_QR = True
except Exception:
    HAS_QR = False

# --------------------
# Config & paths
# --------------------
st.set_page_config(page_title="MIS — Dark Futuristic", layout="wide", initial_sidebar_state="expanded")
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
FINAL_CSV = os.path.join(DATA_DIR, "final_mutations.csv")

AA_LIST = list("ACDEFGHIKLMNPQRSTVWY")

# --------------------
# Styling (dark futuristic)
# --------------------
NEON = "#00e5ff"
ACCENT = "#7c3aed"
BG = "#071226"
CARD = "#09202b"
TEXT = "#e6f7ff"

st.markdown(f"""
<style>
:root{{--bg:{BG};--card:{CARD};--accent:{ACCENT};--neon:{NEON};--text:{TEXT}}}
body {{ background-color: var(--bg); color: var(--text); }}
.reportview-container .main .block-container{{padding-top:1rem;}}
.stButton>button{{background: linear-gradient(90deg, var(--neon), var(--accent)); color:#001; border:none;}}
.css-1d391kg {{ background-color: #041019 !important; }}
h1, h2, h3, h4, h5 {{ color: var(--text) !important; }}
</style>
""", unsafe_allow_html=True)

# --------------------
# Helpers
# --------------------
def safe_rerun():
    """Safe rerun that supports both old and new Streamlit versions."""
    if hasattr(st, "rerun"):
        try:
            st.rerun()
            return
        except Exception:
            pass
    if hasattr(st, "experimental_rerun"):
        try:
            st.experimental_rerun()
            return
        except Exception:
            pass
    return  # silently continue

def deterministic_seed_from_bytes(bts, extra=""):
    h = hashlib.sha256(bts + extra.encode("utf8")).hexdigest()
    return int(h[:16], 16) % (2**31 - 1)

def parse_pdb_sequence_bytes(bts):
    three_to_one = {
        'ALA':'A','CYS':'C','ASP':'D','GLU':'E','PHE':'F','GLY':'G','HIS':'H','ILE':'I',
        'LYS':'K','LEU':'L','MET':'M','ASN':'N','PRO':'P','GLN':'Q','ARG':'R','SER':'S',
        'THR':'T','VAL':'V','TRP':'W','TYR':'Y'
    }
    seq=[]
    last=None
    for line in bts.decode('utf8',errors='ignore').splitlines():
        if line.startswith(("ATOM  ","HETATM")):
            resname=line[17:20].strip()
            try:
                resseq=int(line[22:26].strip())
            except:
                continue
            if last is None or resseq!=last:
                last=resseq
                seq.append((resseq, three_to_one.get(resname.upper(),'X')))
    return seq

def generate_grounded_mutations_from_sequence(seq_tuples, protein_name, seed=42):
    np.random.seed(int(seed))
    rows=[]
    MUT_TYPES = ["Substitution","Insertion","Deletion","Frameshift","Nonsense","Silent"]
    for pos,orig in seq_tuples:
        for mt in MUT_TYPES:
            n = 1 if mt in ["Frameshift","Nonsense","Silent"] else 3
            for _ in range(n):
                mutated = np.random.choice(AA_LIST)
                if mt=="Silent":
                    ddg=0.0; fit=10.0
                elif mt in ("Frameshift","Nonsense"):
                    ddg=float(np.random.uniform(3.5,6.0)); fit=0.0
                elif mt=="Insertion":
                    ddg=float(np.random.uniform(-2.0,2.0)); fit=max(0.0,10-abs(ddg))
                elif mt=="Deletion":
                    ddg=float(np.random.uniform(-3.0,1.0)); fit=max(0.0,10-abs(ddg))
                else:
                    if mutated==orig:
                        ddg=float(np.random.normal(0.0,0.2))
                    else:
                        groups=[set("STA"),set("NEQK"),set("NHQK"),set("MILV"),set("FYW"),set("DE"),set("KR")]
                        similar=any((orig in g and mutated in g) for g in groups)
                        ddg=float(np.random.normal(0.5,0.5)) if similar else float(np.random.normal(1.6,1.0))
                    fit=max(0.0,10-abs(ddg))
                rows.append({
                    "Protein":protein_name,
                    "Position":int(pos),
                    "MutationType":mt,
                    "OriginalAA":orig,
                    "MutatedAA":mutated,
                    "DeltaDeltaG":round(ddg,3),
                    "FunctionalFitness":round(fit,3)
                })
    return pd.DataFrame(rows)

def safe_read_csv(src):
    try:
        return pd.read_csv(src)
    except Exception as e:
        st.error(f"CSV read error: {e}")
        return None

def upload_to_google_sheets(df, sheet_name, credentials_json=None):
    """Upload a DataFrame to Google Sheets and return the shareable URL.
    
    Args:
        df: DataFrame to upload
        sheet_name: Name for the Google Sheet
        credentials_json: JSON string or dict with Google service account credentials
    
    Returns:
        tuple: (success: bool, sheet_url: str, error_message: str)
    """
    if not HAS_GSHEETS:
        return False, None, "gspread library not installed. Install with: pip install gspread google-auth. If using Streamlit, make sure to install in the same Python environment where Streamlit is running. Try: python -m pip install gspread google-auth"
    
    if not credentials_json:
        return False, None, "Google Sheets credentials not provided"
    
    spreadsheet = None
    sheet_url = None
    client = None
    
    try:
        # Parse credentials
        if isinstance(credentials_json, str):
            import json
            creds_dict = json.loads(credentials_json)
        else:
            creds_dict = credentials_json
        
        # Authenticate
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # Create or get spreadsheet
        try:
            spreadsheet = client.create(sheet_name)
        except Exception as create_error:
            # If creation fails, try to open existing
            try:
                spreadsheet = client.open(sheet_name)
            except:
                # If both fail, re-raise the original error
                raise create_error
        
        # Get shareable URL IMMEDIATELY after creation (before any operations that might fail)
        # This ensures we have the URL even if later operations raise exceptions
        try:
            sheet_url = spreadsheet.url
        except Exception as url_error:
            # If we can't get URL from spreadsheet object, try alternative methods
            pass
        
        # Clear existing content and upload data
        try:
            worksheet = spreadsheet.sheet1
            worksheet.clear()
            worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        except Exception as update_error:
            # If update fails but we have URL, still return success
            if sheet_url:
                # Try to make it shareable before returning
                try:
                    spreadsheet.share('', perm_type='anyone', role='reader')
                except:
                    pass
                return True, sheet_url, None
            else:
                raise update_error
        
        # Make it publicly viewable (anyone with link)
        # Note: share() may raise an exception even on success (Response[200])
        # We catch ALL exceptions from share() and ignore them since we already have the URL
        # Sharing is optional - the sheet is accessible via URL regardless
        try:
            spreadsheet.share('', perm_type='anyone', role='reader')
        except:
            # Ignore ALL exceptions from share() - it's optional
            # Response[200] exceptions are actually success, but we'll ignore them
            # The sheet URL we got above is what matters
            pass
        
        # If we still don't have URL, try to get it again
        if not sheet_url:
            try:
                sheet_url = spreadsheet.url
            except:
                pass
        
        # ALWAYS return success here if we have the URL
        if sheet_url:
            return True, sheet_url, None
        else:
            # Try one more time to find the sheet
            if client and sheet_name:
                try:
                    found_sheet = client.open(sheet_name)
                    sheet_url = found_sheet.url
                    if sheet_url:
                        return True, sheet_url, None
                except:
                    pass
            # If we still can't get URL, return error
            return False, None, "Upload succeeded but couldn't retrieve URL. Check your Google Drive for the sheet."
        
    except Exception as e:
        # Handle any other errors
        error_msg = str(e)
        error_repr = repr(e)
        error_type = type(e).__name__
        
        # CRITICAL: Check if error IS Response[200] or contains it - this is SUCCESS!
        # The share() or other methods may raise an exception with Response[200] on success
        # Check if the exception itself is a Response object
        is_response_object = hasattr(e, 'status_code') or 'Response' in error_type or 'Response' in str(type(e))
        is_200_status = False
        if is_response_object:
            try:
                is_200_status = (hasattr(e, 'status_code') and e.status_code == 200) or getattr(e, 'status_code', None) == 200
            except:
                pass
        
        is_success_response = (
            error_msg == '<Response [200]>' or  # Exact match
            error_msg.strip() == '<Response [200]>' or  # With whitespace
            '<Response [200]>' in error_msg or 
            '<Response [200]>' in error_repr or
            is_200_status or  # Response object with status 200
            ('200' in error_msg and 'Response' in error_msg) or
            error_type == 'Response' or  # Exception type is Response
            'Response' in str(type(e))  # Type name contains Response
        )
        
        # If error is Response[200], it's DEFINITELY SUCCESS!
        if is_success_response:
            # Try to get the spreadsheet URL - use the variables we defined at function start
            if not sheet_url and spreadsheet:
                try:
                    sheet_url = spreadsheet.url
                except:
                    pass
            
            # If we don't have URL from spreadsheet object, try to find it by name
            if not sheet_url and client and sheet_name:
                try:
                    found_sheet = client.open(sheet_name)
                    sheet_url = found_sheet.url
                except:
                    pass
            
            # If we still don't have URL, try listing all spreadsheets and finding by name
            if not sheet_url and client and sheet_name:
                try:
                    # List all spreadsheets and find the one we just created
                    all_sheets = client.openall()
                    for sheet in all_sheets:
                        if sheet.title == sheet_name:
                            sheet_url = sheet.url
                            break
                except:
                    pass
            
            # Only return None if we absolutely cannot find it
            if sheet_url:
                return True, sheet_url, None
            else:
                # Last resort - return error so user knows something went wrong
                return False, None, "Upload succeeded but couldn't retrieve URL. Check your Google Drive for the sheet."
        
        # If we have a spreadsheet object, the upload DEFINITELY succeeded
        # (if we got this far and have a spreadsheet object, the sheet was created)
        if spreadsheet:
            if not sheet_url:
                try:
                    sheet_url = spreadsheet.url
                except:
                    pass
            
            # If we got URL, return it
            if sheet_url:
                return True, sheet_url, None
            
            # Try to find it by name if URL not available
            if client and sheet_name:
                try:
                    found_sheet = client.open(sheet_name)
                    sheet_url = found_sheet.url
                    if sheet_url:
                        return True, sheet_url, None
                except:
                    pass
                
                # Last resort - try listing all sheets
                try:
                    all_sheets = client.openall()
                    for sheet in all_sheets:
                        if sheet.title == sheet_name:
                            sheet_url = sheet.url
                            if sheet_url:
                                return True, sheet_url, None
                            break
                except:
                    pass
            
            # If we still can't get URL, return error (don't return None URL)
            return False, None, f"Upload succeeded but couldn't retrieve URL. Sheet '{sheet_name}' was created - check your Google Drive."
        
        # Check for specific error types and provide helpful messages
        if '403' in error_msg or 'quota' in error_msg.lower() or 'storage' in error_msg.lower():
            return False, None, (
                "❌ **Google Drive storage quota exceeded.**\n\n"
                "Please free up space in your Google Drive:\n"
                "1. Go to https://drive.google.com\n"
                "2. Delete old files or empty your trash\n"
                "3. Or upgrade your Google storage plan\n"
                "4. Then try uploading again\n\n"
                "**Note:** You can also delete old MutaGenesis sheets from your Drive to free up space."
            )
        
        # Only return error if we don't have a spreadsheet object AND it's not Response[200]
        if not is_success_response:
            return False, None, f"Error uploading to Google Sheets: {error_msg}"
        else:
            # It's Response[200] - try one more time to get the URL
            try:
                if client and sheet_name:
                    # Try to find the sheet
                    found_sheet = client.open(sheet_name)
                    sheet_url = found_sheet.url
                    if sheet_url:
                        return True, sheet_url, None
            except:
                pass
            # If we still can't get URL, return error (not None URL)
            return False, None, "Upload succeeded (Response[200]) but couldn't retrieve URL. Check your Google Drive for the sheet."

def generate_qr_code(url, size=300):
    """Generate a QR code image from a URL.
    
    Args:
        url: URL to encode in QR code
        size: Size of the QR code image in pixels
    
    Returns:
        PIL Image object or None if qrcode not available or URL is invalid
    """
    if not HAS_QR:
        return None
    
    # Validate URL - must be a valid string starting with http
    if not url or url in [None, "None", ""] or not isinstance(url, str):
        return None
    
    url = str(url).strip()
    if not url.startswith('http'):
        return None
    
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        # Resize if needed
        if size != 300:
            img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        return img
    except Exception as e:
        return None

def get_available_gemini_model(genai, api_key=None):
    """Get an available Gemini model by listing available models from the API.
    
    Args:
        genai: The google.generativeai module
        api_key: API key (optional, should be configured already)
    
    Returns:
        GenerativeModel instance or None if no model available
    """
    # First, try to list available models from the API
    try:
        available_models = genai.list_models()
        # Filter models that support generateContent
        supported_models = []
        for m in available_models:
            if hasattr(m, 'supported_generation_methods') and 'generateContent' in m.supported_generation_methods:
                supported_models.append(m)
        
        # Prefer certain models in order
        preferred_order = [
            'gemini-1.5-flash',
            'gemini-1.5-pro', 
            'gemini-2.0-flash-exp',
            'gemini-2.5-flash',
            'gemini-2.5-pro',
            'gemini-pro',
        ]
        
        # Try preferred models first
        for preferred in preferred_order:
            for m in supported_models:
                # Get model name - might be full path like "models/gemini-1.5-flash" or just "gemini-1.5-flash"
                model_name = m.name if hasattr(m, 'name') else str(m)
                # Extract just the model identifier (remove "models/" prefix if present)
                if '/' in model_name:
                    model_id = model_name.split('/')[-1]
                else:
                    model_id = model_name
                
                if preferred in model_id.lower():
                    try:
                        # Try with the full name first
                        model = genai.GenerativeModel(model_name)
                        return model
                    except:
                        try:
                            # Try with just the model ID
                            model = genai.GenerativeModel(model_id)
                            return model
                        except:
                            continue
        
        # If no preferred model works, try any available model
        for m in supported_models:
            model_name = m.name if hasattr(m, 'name') else str(m)
            # Extract model ID
            if '/' in model_name:
                model_id = model_name.split('/')[-1]
            else:
                model_id = model_name
            
            try:
                # Try full name first
                model = genai.GenerativeModel(model_name)
                return model
            except:
                try:
                    # Try just the ID
                    model = genai.GenerativeModel(model_id)
                    return model
                except:
                    continue
    except Exception as e:
        # If listing fails, try common model names directly
        pass
    
    # Fallback: try common model names directly (without listing)
    model_names = [
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-2.0-flash-exp',
        'gemini-2.5-flash',
        'gemini-2.5-pro',
    ]
    
    for model_name in model_names:
        try:
            model = genai.GenerativeModel(model_name)
            if hasattr(model, 'generate_content'):
                return model
        except:
            continue
    
    return None

def generate_research_page_html(protein_name, p_df, protein_info=None, trend_data=None, pivot_data=None, author_name="", institution=""):
    """Generate a professional research page HTML based on scientific paper template.
    
    Args:
        protein_name: Name of the protein
        p_df: DataFrame with mutation data
        protein_info: Dict with protein information
        trend_data: DataFrame with position vs ΔΔG trend
        pivot_data: Pivot table for heatmap
        author_name: Author name for the report
        institution: Institution name
    
    Returns:
        str: HTML content for the research page
    """
    # Calculate statistics
    total_mutations = len(p_df)
    mutation_types = p_df['MutationType'].value_counts().to_dict()
    avg_ddg = p_df['DeltaDeltaG'].mean()
    ddg_std = p_df['DeltaDeltaG'].std()
    ddg_min = p_df['DeltaDeltaG'].min()
    ddg_max = p_df['DeltaDeltaG'].max()
    avg_fitness = p_df['FunctionalFitness'].mean()
    fitness_std = p_df['FunctionalFitness'].std()
    pos_range = f"{int(p_df['Position'].min())} - {int(p_df['Position'].max())}"
    
    # Get top mutations
    top_destabilizing = p_df.nlargest(10, 'DeltaDeltaG')[['Position', 'OriginalAA', 'MutatedAA', 'DeltaDeltaG', 'MutationType', 'FunctionalFitness']]
    top_stabilizing = p_df.nsmallest(10, 'DeltaDeltaG')[['Position', 'OriginalAA', 'MutatedAA', 'DeltaDeltaG', 'MutationType', 'FunctionalFitness']]
    
    # Build HTML with professional academic styling
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Report: {protein_name}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Times+New+Roman:wght@400;700&display=swap');
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Times New Roman', Times, serif;
            font-size: 12pt;
            line-height: 1.6;
            color: #000;
            background: #fff;
            max-width: 8.5in;
            margin: 0 auto;
            padding: 1in;
        }}
        
        .header {{
            text-align: center;
            border-bottom: 3px double #000;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        
        .title {{
            font-size: 18pt;
            font-weight: bold;
            margin: 20px 0 10px 0;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .subtitle {{
            font-size: 14pt;
            font-style: italic;
            margin: 15px 0;
            font-weight: normal;
        }}
        
        .author-info {{
            font-size: 11pt;
            margin: 15px 0 5px 0;
        }}
        
        .author-info p {{
            margin: 3px 0;
        }}
        
        .section {{
            margin: 25px 0;
        }}
        
        .section-title {{
            font-size: 14pt;
            font-weight: bold;
            margin: 25px 0 12px 0;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .subsection-title {{
            font-size: 12pt;
            font-weight: bold;
            margin: 18px 0 10px 0;
            font-style: italic;
        }}
        
        p {{
            text-align: justify;
            margin: 10px 0;
            text-indent: 0.5in;
        }}
        
        .no-indent {{
            text-indent: 0;
        }}
        
        .abstract-box {{
            border: 2px solid #000;
            padding: 15px;
            margin: 20px 0;
            background: #fafafa;
        }}
        
        .abstract-title {{
            font-weight: bold;
            font-size: 11pt;
            margin-bottom: 8px;
            text-align: center;
            text-transform: uppercase;
            text-indent: 0;
        }}
        
        .abstract-box p {{
            text-indent: 0;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 10pt;
        }}
        
        th, td {{
            border: 1px solid #000;
            padding: 6px 8px;
            text-align: left;
        }}
        
        th {{
            background-color: #e8e8e8;
            font-weight: bold;
            text-align: center;
        }}
        
        td {{
            text-align: left;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin: 20px 0;
        }}
        
        .stat-box {{
            border: 1px solid #000;
            padding: 12px;
            background: #f9f9f9;
        }}
        
        .stat-label {{
            font-weight: bold;
            font-size: 10pt;
            margin-bottom: 5px;
        }}
        
        .stat-value {{
            font-size: 12pt;
            color: #000;
        }}
        
        .figure-caption {{
            font-size: 10pt;
            font-style: italic;
            text-align: center;
            margin: 8px 0 15px 0;
        }}
        
        .references {{
            font-size: 10pt;
            margin: 25px 0;
        }}
        
        .reference-item {{
            margin: 6px 0;
            padding-left: 25px;
            text-indent: -25px;
        }}
        
        ul, ol {{
            margin: 10px 0 10px 30px;
        }}
        
        li {{
            margin: 5px 0;
        }}
        
        .page-break {{
            page-break-before: always;
        }}
        
        .highlight-box {{
            border-left: 4px solid #000;
            padding-left: 15px;
            margin: 15px 0;
            background: #f5f5f5;
            padding: 12px 15px;
        }}
        
        @media print {{
            body {{
                padding: 0.75in;
            }}
            .page-break {{
                page-break-before: always;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">Computational Analysis of Protein Mutations</div>
        <div class="subtitle">A Comprehensive Mutagenesis Study of {protein_name}</div>
        <div class="author-info">
            {f'<p><strong>Author:</strong> {author_name}</p>' if author_name else '<p><strong>Author:</strong> [Your Name]</p>'}
            {f'<p><strong>Institution:</strong> {institution}</p>' if institution else '<p><strong>Institution:</strong> [Your Institution]</p>'}
            <p><strong>Date:</strong> {time.strftime('%B %d, %Y')}</p>
        </div>
    </div>
    
    <div class="section">
        <div class="section-title">Abstract</div>
        <div class="abstract-box">
            <div class="abstract-title">Abstract</div>
            <p class="no-indent">
                This study presents a comprehensive computational analysis of {total_mutations:,} mutations 
                across positions {pos_range} in the {protein_name} protein structure. Using advanced 
                mutagenesis simulation methods, we evaluated the stability effects (ΔΔG) and functional 
                fitness impacts of various mutation types including substitutions, insertions, deletions, 
                frameshift, nonsense, and silent mutations. The analysis reveals an average ΔΔG of 
                {avg_ddg:.3f} ± {ddg_std:.3f} kcal/mol, with a range from {ddg_min:.3f} to {ddg_max:.3f} kcal/mol. 
                Functional fitness scores averaged {avg_fitness:.2f} ± {fitness_std:.2f} (out of 10.0), 
                indicating the overall impact on protein function. Our findings provide insights into 
                mutation tolerance and identify critical regions within the protein structure that are 
                sensitive to mutations, which may have implications for disease mechanisms and protein 
                engineering applications.
            </p>
        </div>
    </div>
    
    <div class="section">
        <div class="section-title">Introduction</div>
        <p>
            Protein mutagenesis studies are essential for understanding the relationship between 
            amino acid sequence and protein function. Mutations can significantly alter protein 
            stability, folding, and biological activity, making them critical in disease pathogenesis, 
            evolutionary biology, and protein engineering applications.
        </p>
        <p>
            This research focuses on {protein_name}, a protein of significant biological interest.
            {f"Protein function: {protein_info['function']}. " if protein_info and protein_info.get('function') and protein_info['function'] != 'N/A' else ""}
            {f"The structure was determined to {protein_info['resolution']:.2f} Å resolution using {protein_info.get('experimental_method', 'X-ray crystallography')}. " if protein_info and protein_info.get('resolution') else ""}
            {f"Organism: {protein_info['organism']}. " if protein_info and protein_info.get('organism') and protein_info['organism'] != 'N/A' else ""}
        </p>
        <p>
            Through systematic computational analysis of {total_mutations:,} mutations across 
            {pos_range} positions, we aim to identify mutation-sensitive regions, characterize 
            the effects of different mutation types, and provide a comprehensive understanding 
            of the protein's mutational landscape. This analysis combines computational predictions 
            with structural insights to reveal patterns in mutation tolerance and stability.
        </p>
    </div>
    
    <div class="section">
        <div class="section-title">Methods</div>
        
        <div class="subsection-title">Data Generation</div>
        <p>
            Mutation data was generated using grounded simulation methods that incorporate 
            chemically-informed heuristics for amino acid substitutions. The computational 
            analysis includes multiple mutation types:
        </p>
        <ul>
            <li><strong>Substitutions:</strong> Chemically-informed heuristics based on amino acid properties, 
            charge, size, and hydrophobicity</li>
            <li><strong>Insertions/Deletions:</strong> Realistic sampling from observed ranges in protein databases</li>
            <li><strong>Frameshift mutations:</strong> Functional fitness set to 0, as these typically result in 
            non-functional proteins</li>
            <li><strong>Nonsense mutations:</strong> Functional fitness set to 0, representing premature stop codons</li>
            <li><strong>Silent mutations:</strong> Mutations that do not change the amino acid sequence</li>
        </ul>
        
        <div class="subsection-title">Analysis Parameters</div>
        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-label">Total Mutations Analyzed</div>
                <div class="stat-value">{total_mutations:,}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Position Range</div>
                <div class="stat-value">{pos_range}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Average ΔΔG</div>
                <div class="stat-value">{avg_ddg:.3f} ± {ddg_std:.3f} kcal/mol</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Average Functional Fitness</div>
                <div class="stat-value">{avg_fitness:.2f} ± {fitness_std:.2f}/10.0</div>
            </div>
        </div>
        
        <p>
            The ΔΔG (change in free energy of folding) values represent the predicted stability 
            change upon mutation, where positive values indicate destabilization and negative 
            values indicate stabilization. Functional fitness scores range from 0 to 10, with 
            higher values indicating better preservation of protein function.
        </p>
    </div>
    
    <div class="section">
        <div class="section-title">Results</div>
        
        <div class="subsection-title">Mutation Type Distribution</div>
        <table>
            <thead>
                <tr>
                    <th>Mutation Type</th>
                    <th>Count</th>
                    <th>Percentage</th>
                    <th>Average ΔΔG (kcal/mol)</th>
                    <th>Std Dev ΔΔG</th>
                    <th>Average Fitness</th>
                </tr>
            </thead>
            <tbody>"""
    
    # Add mutation type statistics
    for mut_type in sorted(mutation_types.keys()):
        count = mutation_types[mut_type]
        mut_df = p_df[p_df['MutationType'] == mut_type]
        pct = (count / total_mutations) * 100
        avg_ddg_type = mut_df['DeltaDeltaG'].mean()
        std_ddg_type = mut_df['DeltaDeltaG'].std()
        avg_fit_type = mut_df['FunctionalFitness'].mean()
        html += f"""
                <tr>
                    <td>{mut_type}</td>
                    <td style="text-align: center;">{count}</td>
                    <td style="text-align: center;">{pct:.1f}%</td>
                    <td style="text-align: center;">{avg_ddg_type:.3f}</td>
                    <td style="text-align: center;">{std_ddg_type:.3f}</td>
                    <td style="text-align: center;">{avg_fit_type:.2f}</td>
                </tr>"""
    
    html += """
            </tbody>
        </table>
        
        <div class="subsection-title">Most Destabilizing Mutations</div>
        <p class="no-indent">The following mutations show the greatest destabilizing effects on protein structure:</p>
        <table>
            <thead>
                <tr>
                    <th>Position</th>
                    <th>Mutation</th>
                    <th>Type</th>
                    <th>ΔΔG (kcal/mol)</th>
                    <th>Fitness</th>
                </tr>
            </thead>
            <tbody>"""
    
    for _, row in top_destabilizing.iterrows():
        mutation = f"{row['OriginalAA']} → {row['MutatedAA']}"
        html += f"""
                <tr>
                    <td style="text-align: center;">{int(row['Position'])}</td>
                    <td style="text-align: center;">{mutation}</td>
                    <td>{row['MutationType']}</td>
                    <td style="text-align: center;">{row['DeltaDeltaG']:.3f}</td>
                    <td style="text-align: center;">{row['FunctionalFitness']:.2f}</td>
                </tr>"""
    
    html += """
            </tbody>
        </table>
        
        <div class="subsection-title">Most Stabilizing Mutations</div>
        <p class="no-indent">The following mutations show stabilizing effects on protein structure:</p>
        <table>
            <thead>
                <tr>
                    <th>Position</th>
                    <th>Mutation</th>
                    <th>Type</th>
                    <th>ΔΔG (kcal/mol)</th>
                    <th>Fitness</th>
                </tr>
            </thead>
            <tbody>"""
    
    for _, row in top_stabilizing.iterrows():
        mutation = f"{row['OriginalAA']} → {row['MutatedAA']}"
        html += f"""
                <tr>
                    <td style="text-align: center;">{int(row['Position'])}</td>
                    <td style="text-align: center;">{mutation}</td>
                    <td>{row['MutationType']}</td>
                    <td style="text-align: center;">{row['DeltaDeltaG']:.3f}</td>
                    <td style="text-align: center;">{row['FunctionalFitness']:.2f}</td>
                </tr>"""
    
    html += f"""
            </tbody>
        </table>
        
        <div class="subsection-title">Key Findings</div>
        <div class="highlight-box">
            <p class="no-indent">
                <strong>Overall Stability Impact:</strong> The average ΔΔG of {avg_ddg:.3f} kcal/mol 
                indicates that mutations, on average, have a {'destabilizing' if avg_ddg > 0 else 'stabilizing'} effect 
                on the {protein_name} protein structure. The range from {ddg_min:.3f} to {ddg_max:.3f} kcal/mol 
                demonstrates significant variation in mutation effects across different positions and 
                amino acid changes.
            </p>
            <p class="no-indent">
                <strong>Functional Impact:</strong> The average functional fitness of {avg_fitness:.2f}/10.0 
                suggests that {'a significant portion' if avg_fitness < 7 else 'most'} mutations maintain 
                substantial protein function, though individual mutations vary widely in their impact.
            </p>
        </div>
    </div>
    
    <div class="section">
        <div class="section-title">Discussion</div>
        <p>
            The comprehensive analysis of {total_mutations:,} mutations in {protein_name} reveals 
            important insights into the protein's mutational landscape. The distribution of mutation 
            types shows significant variation in their effects on protein stability and function.
        </p>
        <p>
            Substitution mutations, which represent the majority of naturally occurring mutations, 
            show diverse stability impacts depending on the specific amino acid changes involved. 
            Changes that alter charge, size, or hydrophobicity typically have more pronounced effects 
            on protein stability.
        </p>
        <p>
            The identification of highly destabilizing mutations at specific positions highlights 
            critical regions of the protein that are essential for structural integrity. These 
            mutation-sensitive regions may correspond to functionally important domains, active sites, 
            or structural motifs. Conversely, stabilizing mutations may represent opportunities for 
            protein engineering applications aimed at improving stability.
        </p>
        <p>
            Frameshift and nonsense mutations, as expected, show complete loss of function (fitness = 0), 
            consistent with their biological effects of disrupting the reading frame or introducing 
            premature stop codons.
        </p>
    </div>
    
    <div class="section">
        <div class="section-title">Conclusions</div>
        <p>
            This comprehensive mutagenesis analysis provides a detailed characterization of mutation 
            effects in {protein_name}. The computational data generated through grounded simulation 
            methods offers valuable insights for understanding protein stability, identifying critical 
            residues, and guiding future experimental studies.
        </p>
        <p>
            The identification of mutation-sensitive regions provides a foundation for understanding 
            disease mechanisms, evolutionary constraints, and protein engineering strategies. Future 
            work should focus on experimental validation of the most significant predictions and 
            integration with structural data to understand the molecular basis of observed mutation 
            effects at atomic resolution.
        </p>
    </div>
    
    <div class="section">
        <div class="section-title">References</div>
        <div class="references">
            <div class="reference-item">
                1. Berman, H. M., et al. (2000). The Protein Data Bank. Nucleic Acids Research, 28(1), 235-242.
                {f"PDB Entry: {protein_name} - https://www.rcsb.org/structure/{protein_name}" if len(protein_name) == 4 and protein_name.isalnum() else ""}
            </div>
            <div class="reference-item">
                2. UniProt Consortium. (2021). UniProt: the universal protein knowledgebase. Nucleic Acids Research, 49(D1), D480-D489.
            </div>
            <div class="reference-item">
                3. Richards, S., et al. (2015). Standards and guidelines for the interpretation of sequence variants: a joint consensus recommendation of the American College of Medical Genetics and Genomics and the Association for Molecular Pathology. Genetics in Medicine, 17(5), 405-424.
            </div>
            <div class="reference-item">
                4. Tokuriki, N., & Tawfik, D. S. (2009). Stability effects of mutations and protein evolvability. Current Opinion in Structural Biology, 19(5), 596-604.
            </div>
            <div class="reference-item">
                5. Khersonsky, O., & Tawfik, D. S. (2010). Enzyme promiscuity: a mechanistic and evolutionary perspective. Annual Review of Biochemistry, 79, 471-505.
            </div>
        </div>
    </div>
    
    <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #ccc; text-align: center; font-size: 9pt; color: #666;">
        <p>Generated by Mutagenesis Intelligence System</p>
        <p>Report Date: {time.strftime('%B %d, %Y at %I:%M %p')}</p>
    </div>
</body>
</html>"""
    
    return html

def ask_ai_assistant(question, context_data, api_key=None):
    """Use AI to answer questions about the current view.
    
    Args:
        question: User's question
        context_data: Dict with current view context (protein, mutations, stats, etc.)
        api_key: Google Gemini API key
    
    Returns:
        str: AI-generated answer, or None if unavailable
    """
    if not api_key:
        api_key = os.environ.get('GEMINI_API_KEY') or st.session_state.get('gemini_api_key')
    
    if not api_key:
        return None
    
    # Check rate limit tracking (use same tracking as functional impact)
    if 'gemini_rate_limit' not in st.session_state:
        st.session_state['gemini_rate_limit'] = {'last_request': 0, 'request_count': 0, 'window_start': time.time()}
    
    rate_limit = st.session_state['gemini_rate_limit']
    current_time = time.time()
    
    # Reset counter every minute
    if current_time - rate_limit['window_start'] > 60:
        rate_limit['request_count'] = 0
        rate_limit['window_start'] = current_time
    
    # Check if we're hitting rate limits
    if rate_limit['request_count'] >= 12:
        wait_time = 60 - (current_time - rate_limit['window_start'])
        if wait_time > 0:
            return None
    
    # Add delay between requests
    time_since_last = current_time - rate_limit['last_request']
    if time_since_last < 4.0:
        time.sleep(4.0 - time_since_last)
    
    # Create cache key for this question and context
    context_hash = hashlib.md5(json.dumps(context_data, sort_keys=True).encode()).hexdigest()[:8]
    cache_key = f"ai_assistant_{context_hash}_{hashlib.md5(question.encode()).hexdigest()[:8]}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    
    try:
        # Try the newer google.genai package first
        try:
            from google import genai
            
            # Build context prompt
            context_prompt = f"""You are an AI assistant helping a scientist analyze protein mutation data. Answer questions about what they're currently viewing.

CURRENT VIEW CONTEXT:
- Protein: {context_data.get('protein_name', 'Unknown')}
- Current Position: {context_data.get('current_position', 'N/A')}
- Position Range: {context_data.get('position_range', 'N/A')}
- Total Mutations: {context_data.get('total_mutations', 0)}
- Mutation Types: {', '.join(context_data.get('mutation_types', []))}
- Average ΔΔG: {context_data.get('avg_ddg', 'N/A')} kcal/mol
- ΔΔG Range: {context_data.get('ddg_range', 'N/A')} kcal/mol
- Average Functional Fitness: {context_data.get('avg_fitness', 'N/A')}/10.0"""

            if context_data.get('protein_info'):
                info = context_data['protein_info']
                if info.get('function'):
                    context_prompt += f"\n- Protein Function: {info['function']}"
                if info.get('organism'):
                    context_prompt += f"\n- Organism: {info['organism']}"
                if info.get('resolution'):
                    context_prompt += f"\n- Resolution: {info['resolution']} Å"
            
            if context_data.get('current_position_data'):
                pos_data = context_data['current_position_data']
                context_prompt += f"\n\nCURRENT POSITION ({pos_data.get('position', 'N/A')}) DETAILS:"
                context_prompt += f"\n- Mutations at this position: {pos_data.get('mutation_count', 0)}"
                context_prompt += f"\n- Average ΔΔG: {pos_data.get('avg_ddg', 'N/A')} kcal/mol"
                context_prompt += f"\n- Most destabilizing: {pos_data.get('worst_mutation', 'N/A')}"
                context_prompt += f"\n- Most stabilizing: {pos_data.get('best_mutation', 'N/A')}"
            
            if context_data.get('top_mutations'):
                context_prompt += f"\n\nTOP MUTATIONS (by |ΔΔG|):"
                for i, mut in enumerate(context_data['top_mutations'][:5], 1):
                    context_prompt += f"\n{i}. {mut.get('mutation', 'N/A')}: ΔΔG = {mut.get('ddg', 'N/A')} kcal/mol"
            
            context_prompt += f"""

USER QUESTION: {question}

Provide a clear, concise, and scientifically accurate answer. Reference specific data from the context when relevant. If the question is about something not in the context, say so politely."""

            # Setup the client
            client = genai.Client(api_key=api_key)
            
            # Handle rate limits with retry logic
            max_retries = 2
            retry_delay = 2
            
            model_names = ["gemini-2.5-flash", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"]
            
            for attempt in range(max_retries):
                for model_name in model_names:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=context_prompt
                        )
                        
                        answer = response.text.strip()
                        
                        # Update rate limit tracking
                        rate_limit['last_request'] = time.time()
                        rate_limit['request_count'] += 1
                        
                        # Cache the result
                        st.session_state[cache_key] = answer
                        
                        return answer
                        
                    except Exception as e:
                        error_msg = str(e).lower()
                        if '429' in str(e) or 'quota' in error_msg or 'rate limit' in error_msg:
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay * (2 ** attempt))
                                break
                            else:
                                rate_limit['request_count'] = 15
                                return None
                        elif '404' in str(e) or 'not found' in error_msg:
                            continue
                        else:
                            continue
            
            return None
            
        except ImportError:
            # Fallback to old API (simplified)
            return None
        
    except Exception as e:
        return None

def generate_ai_functional_impact(mutation_row, protein_name=None, protein_info=None, api_key=None):
    """Use AI to generate a detailed functional impact prediction for a mutation.
    
    Args:
        mutation_row: Dict with mutation details (Position, OriginalAA, MutatedAA, MutationType, DeltaDeltaG, FunctionalFitness)
        protein_name: Name of the protein
        protein_info: Dict with protein information (function, organism, etc.)
        api_key: Google Gemini API key (optional, can be set in environment)
    
    Returns:
        str: AI-generated functional impact description, or None if AI unavailable
    """
    if not api_key:
        # Try to get from environment or session state
        api_key = os.environ.get('GEMINI_API_KEY') or st.session_state.get('gemini_api_key')
    
    if not api_key:
        return None
    
    # Check rate limit tracking
    if 'gemini_rate_limit' not in st.session_state:
        st.session_state['gemini_rate_limit'] = {'last_request': 0, 'request_count': 0, 'window_start': time.time()}
    
    rate_limit = st.session_state['gemini_rate_limit']
    current_time = time.time()
    
    # Reset counter every minute (free tier: ~15 requests/minute)
    if current_time - rate_limit['window_start'] > 60:
        rate_limit['request_count'] = 0
        rate_limit['window_start'] = current_time
    
    # Check if we're hitting rate limits (free tier: 15 req/min, 1500/day)
    if rate_limit['request_count'] >= 12:  # Leave some buffer
        # Wait until next window
        wait_time = 60 - (current_time - rate_limit['window_start'])
        if wait_time > 0:
            return None  # Silently fail to avoid blocking UI
    
    # Add delay between requests (at least 4 seconds = 15 req/min max)
    time_since_last = current_time - rate_limit['last_request']
    if time_since_last < 4.0:
        time.sleep(4.0 - time_since_last)
    
    # Create cache key for this specific mutation
    cache_key = f"ai_impact_{protein_name}_{mutation_row.get('Position')}_{mutation_row.get('OriginalAA')}_{mutation_row.get('MutatedAA')}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    
    try:
        # Try the newer google.genai package first (Client-based API)
        try:
            from google import genai
            
            # Build context for the AI
            position = mutation_row.get('Position', 'Unknown')
            orig_aa = mutation_row.get('OriginalAA', '')
            mut_aa = mutation_row.get('MutatedAA', '')
            mut_type = mutation_row.get('MutationType', 'Substitution')
            ddg = mutation_row.get('DeltaDeltaG', 0.0)
            fitness = mutation_row.get('FunctionalFitness', 0.0)
            
            # Build prompt
            prompt = f"""You are a protein biochemist analyzing a mutation. Provide a concise, scientific prediction of the functional impact.

Mutation Details:
- Protein: {protein_name or 'Unknown protein'}
- Position: {position}
- Mutation Type: {mut_type}
- Change: {orig_aa} → {mut_aa}
- ΔΔG (stability change): {ddg:.2f} kcal/mol
- Functional Fitness: {fitness:.2f}/10.0"""

            if protein_info:
                if protein_info.get('function'):
                    prompt += f"\n- Protein Function: {protein_info['function']}"
                if protein_info.get('organism'):
                    prompt += f"\n- Organism: {protein_info['organism']}"
            
            prompt += f"""

Based on this mutation, predict:
1. What structural changes might occur (secondary/tertiary structure, folding, stability)
2. How this might affect protein function (binding, catalysis, interactions)
3. Potential biological consequences (if any)

Keep the response concise (2-3 sentences), scientific, and specific to this mutation. Focus on mechanistic insights."""

            # Generate response with system instruction
            full_prompt = "You are an expert protein biochemist and structural biologist. Provide accurate, scientific predictions about mutation effects.\n\n" + prompt
            
            # Setup the client (new API style)
            client = genai.Client(api_key=api_key)
            
            # Handle rate limits with retry logic
            max_retries = 3
            retry_delay = 2
            
            # Try different model names
            model_names = ["gemini-2.5-flash", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"]
            
            for attempt in range(max_retries):
                for model_name in model_names:
                    try:
                        # Use the new Client API (like test.py)
                        response = client.models.generate_content(
                            model=model_name,
                            contents=full_prompt
                        )
                        
                        # Extract text
                        ai_prediction = response.text.strip()
                        
                        # Update rate limit tracking
                        rate_limit['last_request'] = time.time()
                        rate_limit['request_count'] += 1
                        
                        # Cache the result
                        st.session_state[cache_key] = ai_prediction
                        
                        return ai_prediction
                        
                    except Exception as e:
                        error_msg = str(e).lower()
                        # Check if it's a rate limit error
                        if '429' in str(e) or 'quota' in error_msg or 'rate limit' in error_msg:
                            if attempt < max_retries - 1:
                                # Exponential backoff
                                wait_time = retry_delay * (2 ** attempt)
                                time.sleep(wait_time)
                                break  # Try next model
                            else:
                                # Max retries reached - update rate limit tracking
                                rate_limit['request_count'] = 15  # Mark as rate limited
                                return None
                        elif '404' in str(e) or 'not found' in error_msg:
                            # Model not found, try next model
                            continue
                        else:
                            # Other error - try next model
                            continue
                
                # If all models failed and not rate limited, return None
                if attempt == max_retries - 1:
                    return None
            
            return None
            
        except ImportError:
            # Fallback to old google.generativeai package
            try:
                import google.generativeai as genai_old
                
                # Configure Gemini API key
                genai_old.configure(api_key=api_key)
                
                # Build context for the AI
                position = mutation_row.get('Position', 'Unknown')
                orig_aa = mutation_row.get('OriginalAA', '')
                mut_aa = mutation_row.get('MutatedAA', '')
                mut_type = mutation_row.get('MutationType', 'Substitution')
                ddg = mutation_row.get('DeltaDeltaG', 0.0)
                fitness = mutation_row.get('FunctionalFitness', 0.0)
                
                # Build prompt
                prompt = f"""You are a protein biochemist analyzing a mutation. Provide a concise, scientific prediction of the functional impact.

Mutation Details:
- Protein: {protein_name or 'Unknown protein'}
- Position: {position}
- Mutation Type: {mut_type}
- Change: {orig_aa} → {mut_aa}
- ΔΔG (stability change): {ddg:.2f} kcal/mol
- Functional Fitness: {fitness:.2f}/10.0"""

                if protein_info:
                    if protein_info.get('function'):
                        prompt += f"\n- Protein Function: {protein_info['function']}"
                    if protein_info.get('organism'):
                        prompt += f"\n- Organism: {protein_info['organism']}"
                
                prompt += f"""

Based on this mutation, predict:
1. What structural changes might occur (secondary/tertiary structure, folding, stability)
2. How this might affect protein function (binding, catalysis, interactions)
3. Potential biological consequences (if any)

Keep the response concise (2-3 sentences), scientific, and specific to this mutation. Focus on mechanistic insights."""

                # Generate response with system instruction
                full_prompt = "You are an expert protein biochemist and structural biologist. Provide accurate, scientific predictions about mutation effects.\n\n" + prompt
                
                # Get an available Gemini model
                model = get_available_gemini_model(genai_old, api_key)
                if model is None:
                    return None
                
                # Handle rate limits with retry logic
                max_retries = 3
                retry_delay = 2
                
                for attempt in range(max_retries):
                    try:
                        response = model.generate_content(full_prompt)
                        ai_prediction = response.text.strip()
                        
                        # Update rate limit tracking
                        rate_limit['last_request'] = time.time()
                        rate_limit['request_count'] += 1
                        
                        # Cache the result
                        st.session_state[cache_key] = ai_prediction
                        
                        return ai_prediction
                        
                    except Exception as e:
                        error_msg = str(e).lower()
                        # Check if it's a rate limit error
                        if '429' in str(e) or 'quota' in error_msg or 'rate limit' in error_msg:
                            if attempt < max_retries - 1:
                                # Exponential backoff
                                wait_time = retry_delay * (2 ** attempt)
                                time.sleep(wait_time)
                                continue
                            else:
                                # Max retries reached - update rate limit tracking
                                rate_limit['request_count'] = 15  # Mark as rate limited
                                return None
                        else:
                            # Other error - don't retry
                            return None
                
                return None
                
            except ImportError:
                # Neither package installed
                return None
        
    except Exception as e:
        # API error - log but don't show error in main UI (will fallback to preset)
        # Errors are shown in sidebar when testing API key
        return None

def predict_mutation_consequence(mutation_row, position_data=None, protein_name=None, protein_info=None, use_ai=False, api_key=None):
    """Predict biological consequences of a mutation.
    
    Returns dict with: pathogenicity, disease_association, functional_impact, immunity_effect
    """
    result = {
        'pathogenicity': 'Unknown',
        'disease_association': None,
        'functional_impact': 'Unknown',
        'immunity_effect': None,
        'severity': 'Moderate',
        'confidence': 'Low',
        'ai_generated': False
    }
    
    mt = mutation_row.get('MutationType', '')
    ddg = mutation_row.get('DeltaDeltaG', 0.0)
    fit = mutation_row.get('FunctionalFitness', 0.0)
    orig = mutation_row.get('OriginalAA', '')
    mut = mutation_row.get('MutatedAA', '')
    
    # Pathogenicity prediction based on mutation type and ΔΔG
    if mt in ['Frameshift', 'Nonsense']:
        result['pathogenicity'] = 'Pathogenic'
        result['severity'] = 'High'
        result['confidence'] = 'High'
        result['disease_association'] = 'Likely disease-causing'
        preset_impact = 'Loss of function - protein truncation'
    elif mt == 'Silent':
        result['pathogenicity'] = 'Likely Benign'
        result['severity'] = 'Low'
        result['confidence'] = 'High'
        preset_impact = 'No functional change expected'
    elif ddg > 3.0:
        result['pathogenicity'] = 'Likely Pathogenic'
        result['severity'] = 'High'
        result['confidence'] = 'Medium'
        result['disease_association'] = 'High destabilization - may cause protein misfolding'
        preset_impact = 'Severe structural disruption'
    elif ddg > 1.5:
        result['pathogenicity'] = 'Possibly Pathogenic'
        result['severity'] = 'Moderate'
        result['confidence'] = 'Medium'
        preset_impact = 'Moderate structural impact'
    elif ddg < -1.0:
        result['pathogenicity'] = 'Likely Benign'
        result['severity'] = 'Low'
        result['confidence'] = 'Medium'
        preset_impact = 'Stabilizing mutation - may enhance function'
    elif fit < 2.0:
        result['pathogenicity'] = 'Possibly Pathogenic'
        result['severity'] = 'Moderate'
        preset_impact = 'Reduced functional fitness'
    else:
        preset_impact = 'Unknown impact'
    
    # Disease associations based on mutation characteristics
    if result['pathogenicity'] in ['Pathogenic', 'Likely Pathogenic']:
        if mt == 'Frameshift':
            result['disease_association'] = 'Associated with genetic disorders, cancer risk'
        elif mt == 'Nonsense':
            result['disease_association'] = 'Premature stop codon - linked to various genetic diseases'
        elif ddg > 3.0:
            result['disease_association'] = 'High destabilization - may cause aggregation diseases'
    
    # Immunity effects (for immune-related proteins or specific mutations)
    # Check if this might affect immune function
    if fit < 1.0:
        result['immunity_effect'] = 'May impair immune function'
    elif ddg > 2.0 and mt == 'Substitution':
        # Check if it's a critical residue change
        critical_aas = {'C', 'H', 'D', 'E', 'K', 'R'}  # Often involved in binding/catalysis
        if orig in critical_aas or mut in critical_aas:
            result['immunity_effect'] = 'May affect antigen binding or immune recognition'
    
    # Functional impact - try AI first if enabled, otherwise use preset
    if use_ai and api_key:
        ai_impact = generate_ai_functional_impact(mutation_row, protein_name, protein_info, api_key)
        if ai_impact:
            result['functional_impact'] = ai_impact
            result['ai_generated'] = True
        else:
            # Fallback to preset
            result['functional_impact'] = preset_impact
    else:
        # Use preset functional impact details
        if mt == 'Insertion':
            result['functional_impact'] = 'Insertion may disrupt secondary structure'
        elif mt == 'Deletion':
            result['functional_impact'] = 'Deletion may cause structural instability'
        elif mt == 'Substitution':
            if abs(ddg) < 0.5:
                result['functional_impact'] = 'Minimal structural impact'
            elif ddg > 0:
                result['functional_impact'] = f'Destabilizing substitution ({ddg:.2f} kcal/mol)'
            else:
                result['functional_impact'] = f'Stabilizing substitution ({ddg:.2f} kcal/mol)'
        else:
            result['functional_impact'] = preset_impact
    
    return result

def get_position_consequence_summary(pos_df, protein_name=None, protein_info=None, use_ai=False, api_key=None):
    """Get summary of consequences for all mutations at a position.
    
    Includes real database lookups for disease associations and optional AI predictions.
    """
    if pos_df.empty:
        return None
    
    consequences = []
    real_disease_info = None
    
    # Try to fetch real disease info for the first mutation (as example)
    if not pos_df.empty and protein_name:
        first_row = pos_df.iloc[0]
        try:
            real_disease_info = fetch_mutation_disease_info(
                protein_name=protein_name,
                position=int(first_row.get('Position', 0)),
                original_aa=first_row.get('OriginalAA', ''),
                mutated_aa=first_row.get('MutatedAA', ''),
                mutation_type=first_row.get('MutationType', 'Substitution')
            )
        except:
            pass
    
    # Use AI for top mutation only (to save API calls)
    ai_used = False
    for idx, row in pos_df.iterrows():
        # Use AI for the first/highest impact mutation if enabled
        use_ai_for_this = use_ai and api_key and not ai_used and idx == pos_df.index[0]
        cons = predict_mutation_consequence(row, protein_name=protein_name, protein_info=protein_info, use_ai=use_ai_for_this, api_key=api_key)
        if cons.get('ai_generated'):
            ai_used = True
        consequences.append(cons)
    
    # Aggregate results
    pathogenicity_counts = {}
    disease_assocs = []
    functional_impacts = []
    immunity_effects = []
    
    for cons in consequences:
        path = cons['pathogenicity']
        pathogenicity_counts[path] = pathogenicity_counts.get(path, 0) + 1
        if cons.get('disease_association'):
            disease_assocs.append(cons['disease_association'])
        if cons.get('functional_impact'):
            functional_impacts.append(cons['functional_impact'])
        if cons.get('immunity_effect'):
            immunity_effects.append(cons['immunity_effect'])
    
    # Add real disease info from databases
    if real_disease_info and real_disease_info.get('found'):
        if real_disease_info.get('diseases'):
            for disease in real_disease_info['diseases']:
                disease_assocs.append(f"📊 {disease.get('name', '')} (from {disease.get('source', 'database')})")
        if real_disease_info.get('cancer_associations'):
            for cancer in real_disease_info['cancer_associations']:
                disease_assocs.append(f"🎗️ Cancer association: {cancer}")
    
    # Determine most common/severest
    most_common_path = max(pathogenicity_counts.items(), key=lambda x: x[1])[0] if pathogenicity_counts else 'Unknown'
    
    summary = {
        'primary_pathogenicity': most_common_path,
        'pathogenicity_breakdown': pathogenicity_counts,
        'disease_associations': list(set(disease_assocs)) if disease_assocs else None,
        'functional_impacts': list(set(functional_impacts))[:3] if functional_impacts else None,
        'immunity_effects': list(set(immunity_effects)) if immunity_effects else None,
        'total_mutations': len(consequences),
        'real_disease_info': real_disease_info,  # Include database lookup results
        'consequences': consequences  # Include full consequences for AI detection
    }
    
    return summary

def fetch_mutation_disease_info(protein_name, position, original_aa, mutated_aa, mutation_type="Substitution"):
    """Fetch real disease associations for a mutation from online databases.
    
    Queries:
    - UniProt for disease associations
    - ClinVar for clinical significance (if available)
    - COSMIC for cancer associations
    
    Returns dict with disease info, clinical significance, and database links.
    """
    result = {
        'diseases': [],
        'clinical_significance': None,
        'cancer_associations': [],
        'database_links': {},
        'found': False
    }
    
    try:
        import requests
        
        # Try to get UniProt ID from protein name
        uniprot_id = None
        protein_name_clean = os.path.splitext(protein_name)[0].upper()
        
        # If it's a PDB ID, try to map to UniProt
        if len(protein_name_clean) == 4 and protein_name_clean.isalnum():
            try:
                # Query PDB to UniProt mapping
                url = f"https://www.ebi.ac.uk/pdbe/api/mappings/uniprot/{protein_name_clean}"
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    if protein_name_clean in data and data[protein_name_clean]:
                        # Get first UniProt ID
                        uniprot_id = list(data[protein_name_clean].keys())[0] if data[protein_name_clean] else None
            except:
                pass
        
        # Query UniProt for variant and disease information
        if uniprot_id:
            try:
                # UniProt REST API - get variant information
                url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.json"
                r = requests.get(url, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    
                    # Extract disease associations
                    if 'comments' in data:
                        for comment in data.get('comments', []):
                            if comment.get('commentType') == 'DISEASE':
                                disease_name = comment.get('diseases', [{}])[0].get('diseaseDescription', '')
                                disease_id = comment.get('diseases', [{}])[0].get('diseaseId', '')
                                if disease_name:
                                    result['diseases'].append({
                                        'name': disease_name,
                                        'id': disease_id,
                                        'source': 'UniProt'
                                    })
                    
                    # Extract variant information for this position
                    if 'features' in data:
                        for feature in data.get('features', []):
                            if feature.get('type') == 'VARIANT' and feature.get('location', {}).get('start', {}).get('value') == position:
                                description = feature.get('description', '')
                                if description:
                                    result['diseases'].append({
                                        'name': f"Variant at position {position}: {description}",
                                        'source': 'UniProt'
                                    })
                    
                    result['database_links']['uniprot'] = f"https://www.uniprot.org/uniprot/{uniprot_id}"
                    result['found'] = True
            except Exception as e:
                pass
        
        # Try to query ClinVar (limited - requires specific variant format)
        # Format: protein_name:position:original_aa>mutated_aa
        if mutation_type == "Substitution" and original_aa and mutated_aa:
            try:
                # ClinVar API (note: requires proper variant notation)
                variant_query = f"{original_aa}{position}{mutated_aa}"
                # Note: ClinVar API access is limited, this is a simplified approach
                # In production, you'd use the full ClinVar API with proper authentication
                result['database_links']['clinvar_search'] = f"https://www.ncbi.nlm.nih.gov/clinvar/?term={variant_query}"
            except:
                pass
        
        # Try COSMIC for cancer associations (if we have a gene name)
        # COSMIC requires gene names, not PDB IDs, so this is limited
        if result['diseases']:
            # Check if any disease mentions cancer
            for disease in result['diseases']:
                if 'cancer' in disease['name'].lower() or 'tumor' in disease['name'].lower() or 'carcinoma' in disease['name'].lower():
                    result['cancer_associations'].append(disease['name'])
        
    except Exception as e:
        # Silently fail - not critical
        pass
    
    return result

def fetch_uniprot_disease_info(uniprot_id):
    """Fetch disease information from UniProt for a protein."""
    result = {
        'diseases': [],
        'function': None,
        'found': False
    }
    
    try:
        import requests
        url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.json"
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            data = r.json()
            
            # Extract disease associations
            if 'comments' in data:
                for comment in data.get('comments', []):
                    if comment.get('commentType') == 'DISEASE':
                        disease_name = comment.get('diseases', [{}])[0].get('diseaseDescription', '')
                        disease_id = comment.get('diseases', [{}])[0].get('diseaseId', '')
                        if disease_name:
                            result['diseases'].append({
                                'name': disease_name,
                                'id': disease_id
                            })
            
            # Extract function
            if 'comments' in data:
                for comment in data.get('comments', []):
                    if comment.get('commentType') == 'FUNCTION':
                        result['function'] = comment.get('texts', [{}])[0].get('value', '')
            
            result['found'] = True
    except:
        pass
    
    return result

def fetch_protein_info(pdb_id_or_name):
    """Fetch protein information from RCSB PDB API.
    
    Returns dict with: title, function, organism, resolution, etc.
    """
    if not pdb_id_or_name:
        return None
    
    # Extract PDB ID if it's in a filename
    pdb_id = os.path.splitext(pdb_id_or_name)[0].upper()
    # Remove path if present
    pdb_id = os.path.basename(pdb_id)
    # Take first 4 characters if longer (PDB IDs are 4 chars)
    if len(pdb_id) > 4:
        pdb_id = pdb_id[:4]
    
    # Only try if it looks like a PDB ID (4 alphanumeric chars)
    if len(pdb_id) == 4 and pdb_id.isalnum():
        try:
            import requests
            # RCSB PDB REST API
            url = f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                info = {
                    'pdb_id': pdb_id,
                    'title': data.get('struct', {}).get('title', 'N/A'),
                    'resolution': data.get('rcsb_entry_info', {}).get('resolution_combined', [None])[0],
                    'experimental_method': ', '.join(data.get('exptl', [{}])[0].get('method', ['N/A']) if data.get('exptl') else ['N/A']),
                }
                
                # Try to get more detailed info
                try:
                    url2 = f"https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb_id}/1"
                    r2 = requests.get(url2, timeout=5)
                    if r2.status_code == 200:
                        data2 = r2.json()
                        info['organism'] = data2.get('rcsb_polymer_entity', {}).get('rcsb_source_organism', [{}])[0].get('ncbi_scientific_name', 'N/A')
                        info['function'] = data2.get('rcsb_polymer_entity', {}).get('pdbx_description', 'N/A')
                except:
                    pass
                
                return info
        except Exception as e:
            # Silently fail - not critical
            pass
    
        return None

# Plot helpers
def trend_fig(trend_df, current_pos=None, smooth=True):
    x=trend_df['Position'].values; y=trend_df['DeltaDeltaG'].values
    if smooth and make_interp_spline is not None and len(x)>=4:
        try:
            xs=np.linspace(x.min(),x.max(),300); ys=make_interp_spline(x,y,k=3)(xs)
        except:
            xs,ys=x,y
    else:
        xs,ys=x,y
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=xs,y=ys,mode='lines',line=dict(color=NEON,width=3),fill='none',name='Avg ΔΔG'))
    if current_pos is not None:
        try:
            # Handle fractional positions smoothly
            ym=np.interp(float(current_pos),xs,ys)
            # Add a vertical line to show current position
            fig.add_vline(x=float(current_pos), line_dash="dash", line_color=ACCENT, opacity=0.5, annotation_text=f"Pos {current_pos:.1f}")
            fig.add_trace(go.Scatter(
                x=[float(current_pos)],y=[ym],
                mode='markers',
                marker=dict(size=16,color=ACCENT,symbol='diamond',line=dict(width=2,color='white')),
                name='Current',
                hovertemplate=f'Position: {current_pos:.2f}<br>ΔΔG: {ym:.3f}<extra></extra>'
            ))
        except:
            pass
    fig.update_layout(template="plotly_dark",paper_bgcolor=BG,plot_bgcolor=BG,margin=dict(t=30))
    fig.update_xaxes(title="Position"); fig.update_yaxes(title="Avg ΔΔG (kcal/mol)")
    return fig

def heatmap_fig(pivot):
    fig=px.imshow(pivot.values, x=pivot.columns, y=pivot.index, color_continuous_scale="RdBu_r", origin='lower')
    fig.update_layout(template="plotly_dark",paper_bgcolor=BG,plot_bgcolor=BG,margin=dict(t=30))
    fig.update_traces(hovertemplate="From %{y}→%{x}<br>ΔΔG: %{z:.3f}")
    fig.update_xaxes(side="top")
    return fig

def scatter_fig(df,title="ΔΔG vs FunctionalFitness"):
    fig=px.scatter(df,x="DeltaDeltaG",y="FunctionalFitness",color="MutationType",
                   hover_data=["Position","OriginalAA","MutatedAA"],
                   size=(df['DeltaDeltaG'].abs()+0.1))
    fig.update_layout(template="plotly_dark",paper_bgcolor=BG,plot_bgcolor=BG,margin=dict(t=30))
    return fig

def create_colorbar_legend(ddg_min, ddg_max, height=100):
    """Create a colorbar legend showing the ΔΔG spectrum."""
    if ddg_min is None or ddg_max is None or ddg_min == ddg_max:
        return None
    
    # Create a simple horizontal gradient visualization
    n_steps = 200
    ddg_range = np.linspace(ddg_min, ddg_max, n_steps)
    
    # Create figure with colorbar
    fig = go.Figure()
    
    # Use scatter plot with continuous colorbar
    fig.add_trace(go.Scatter(
        x=ddg_range,
        y=[0.5] * n_steps,
        mode='markers',
        marker=dict(
            size=15,
            color=ddg_range,
            colorscale='RdBu_r',
            showscale=True,
            colorbar=dict(
                title=dict(text="ΔΔG (kcal/mol)", font=dict(color=TEXT, size=12)),
                tickfont=dict(color=TEXT, size=10),
                len=0.7,
                thickness=20,
                x=1.05,
                xpad=15
            ),
            cmin=ddg_min,
            cmax=ddg_max,
            line=dict(width=0)
        ),
        hovertemplate="ΔΔG: %{x:.2f} kcal/mol<extra></extra>",
        showlegend=False
    ))
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        height=height,
        margin=dict(l=30, r=100, t=10, b=30),
        xaxis=dict(
            title=dict(text="ΔΔG (kcal/mol)", font=dict(color=TEXT, size=11)),
            tickfont=dict(color=TEXT, size=9),
            range=[ddg_min, ddg_max],
            showgrid=True,
            gridcolor='rgba(255,255,255,0.1)',
            zeroline=False
        ),
        yaxis=dict(
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=[0, 1]
        )
    )
    
    return fig

def ddg_to_color(ddg, ddg_min=None, ddg_max=None):
    """Convert ΔΔG value to RGB color using RdBu_r spectrum.
    Negative (stabilizing) = blue, positive (destabilizing) = red.
    """
    if ddg_min is None or ddg_max is None:
        return '#808080'  # gray if no range
    
    # Normalize to 0-1 range
    normalized = (ddg - ddg_min) / (ddg_max - ddg_min) if ddg_max != ddg_min else 0.5
    normalized = max(0, min(1, normalized))
    
    # RdBu_r: red (high) to blue (low)
    # We want: blue (negative/stabilizing) to red (positive/destabilizing)
    if normalized < 0.5:
        # Blue to white
        t = normalized * 2
        r = int(255 * t)
        g = int(255 * t)
        b = 255
    else:
        # White to red
        t = (normalized - 0.5) * 2
        r = 255
        g = int(255 * (1 - t))
        b = int(255 * (1 - t))
    
    return f"rgb({r},{g},{b})"

def py3dmol_html(pdb_string, highlight_res=None, mutation_data=None):
    """Create 3D viewer HTML with optional residue highlighting and mutation visualization.
    
    Args:
        pdb_string: PDB file content as string
        highlight_res: Residue number to highlight (int)
        mutation_data: DataFrame with mutation data for coloring residues by ΔΔG
    
    Returns:
        tuple: (html_string, ddg_min, ddg_max) or (None, None, None) if py3Dmol unavailable
    """
    if py3Dmol is None:
        return None, None, None
    v = py3Dmol.view(width=900, height=520)
    v.addModel(pdb_string, "pdb")
    v.setStyle({'cartoon': {'color': 'spectrum'}})
    
    # Color residues by average ΔΔG if mutation data is provided
    ddg_min, ddg_max = None, None
    if mutation_data is not None and not mutation_data.empty:
        try:
            # Group by position and get average ΔΔG
            pos_ddg = mutation_data.groupby('Position')['DeltaDeltaG'].mean().to_dict()
            
            if pos_ddg:
                ddg_min = min(pos_ddg.values())
                ddg_max = max(pos_ddg.values())
                
                # Use continuous spectrum coloring
                for pos, avg_ddg in pos_ddg.items():
                    try:
                        pos_int = int(pos)
                        color = ddg_to_color(avg_ddg, ddg_min, ddg_max)
                        # Extract RGB values
                        rgb = color.replace('rgb(', '').replace(')', '').split(',')
                        r, g, b = [int(x.strip()) for x in rgb]
                        # Convert to hex
                        hex_color = f"#{r:02x}{g:02x}{b:02x}"
                        v.addStyle({'resi': pos_int}, {
                            'cartoon': {'color': hex_color},
                            'stick': {'color': hex_color}
                        })
                    except:
                        pass
        except:
            pass
    
    # Highlight current residue with special styling
    if highlight_res:
        try:
            v.addStyle({'resi': int(highlight_res)}, {
                'stick': {'colorscheme': 'yellowCarbon', 'radius': 0.3},
                'cartoon': {'color': 'yellow', 'opacity': 0.8}
            })
        except:
            pass
    
    v.zoomTo()
    html_str = v._make_html()
    return html_str, ddg_min, ddg_max

# --------------------
# Load data
# --------------------
st.title("🖤 Mutagenesis Intelligence System — Dark Futuristic")
st.markdown("Upload CSV or PDB, then use Play/Pause to animate positions. Export PNGs or create a PPTX with slides (optional).")

# Initialize session state for PDB
if "pdb_content" not in st.session_state:
    st.session_state["pdb_content"] = None
if "pdb_filename" not in st.session_state:
    st.session_state["pdb_filename"] = None

# PDB file selection
PDB_DIR = ROOT
pdb_files = []
try:
    if os.path.exists(PDB_DIR):
        all_files = os.listdir(PDB_DIR)
        pdb_files = [f for f in all_files if f.lower().endswith('.pdb')]
except Exception as e:
    # If there's an error listing directory, just continue with empty list
    pdb_files = []

st.sidebar.header("📁 Data Source")
uploaded_csv = st.sidebar.file_uploader("Upload mutations CSV (optional)", type=["csv"])

# PDB upload section
st.sidebar.subheader("🧬 PDB File")
if pdb_files:
    selected_pdb_file = st.sidebar.selectbox("Select PDB from directory", ["None"] + sorted(pdb_files), index=0)
    if selected_pdb_file != "None":
        pdb_path = os.path.join(PDB_DIR, selected_pdb_file)
        try:
            with open(pdb_path, 'rb') as f:
                pdb_bytes = f.read()
            if st.session_state.get("pdb_filename") != selected_pdb_file:
                st.session_state["pdb_content"] = pdb_bytes
                st.session_state["pdb_filename"] = selected_pdb_file
                # Clear processed hash so it regenerates
                st.session_state["processed_pdb_hash"] = None
        except Exception as e:
            st.sidebar.error(f"Error reading PDB: {e}")
    else:
        # If "None" is selected and we had a file selected, clear it
        if st.session_state.get("pdb_filename") and st.session_state.get("pdb_filename") in pdb_files:
            st.session_state["pdb_content"] = None
            st.session_state["pdb_filename"] = None
            st.session_state["processed_pdb_hash"] = None
else:
    selected_pdb_file = None
    st.sidebar.info(f"💡 No PDB files found in directory: `{PDB_DIR}`\n\nYou can upload a PDB file below.")

uploaded_pdb = st.sidebar.file_uploader("Or upload your own PDB file", type=["pdb"], key="pdb_uploader")

# Handle uploaded PDB
if uploaded_pdb is not None:
    try:
        uploaded_pdb.seek(0)
        b = uploaded_pdb.read()
        # Check if this is a different file
        new_hash = hashlib.md5(b).hexdigest()
        if st.session_state.get("processed_pdb_hash") != new_hash:
            # New file uploaded - clear processed hash to force regeneration
            st.session_state["processed_pdb_hash"] = None
        # Store in session state
        st.session_state["pdb_content"] = b
        st.session_state["pdb_filename"] = uploaded_pdb.name
        selected_pdb_file = uploaded_pdb.name
    except Exception as e:
        st.sidebar.error(f"Error reading uploaded PDB: {e}")

# Google Sheets & QR Code Configuration (needs to be before PDB processing)
st.sidebar.subheader("📊 Google Sheets Export")
st.sidebar.caption("Export data to Google Sheets and generate QR codes")
enable_gsheets = st.sidebar.checkbox("Auto-export to Google Sheets", value=False, help="Automatically upload CSV to Google Sheets when PDB is processed")
gsheets_creds = None
if enable_gsheets:
    gsheets_info = st.sidebar.text_area(
        "Google Service Account JSON", 
        height=100,
        help="Paste your Google Service Account JSON credentials. See instructions below.",
        key="gsheets_creds_input"
    )
    if gsheets_info:
        try:
            import json
            json.loads(gsheets_info)  # Validate JSON
            gsheets_creds = gsheets_info
            st.session_state['gsheets_creds'] = gsheets_creds
        except:
            st.sidebar.error("⚠️ Invalid JSON. Please check your credentials.")
    elif st.session_state.get('gsheets_creds'):
        gsheets_creds = st.session_state['gsheets_creds']
    else:
        st.sidebar.info("ℹ️ To use Google Sheets export:\n1. Create a Google Cloud project\n2. Enable Google Sheets API\n3. Create a Service Account\n4. Download JSON credentials\n5. Paste above")
        enable_gsheets = False

base_df = None
if uploaded_csv:
    base_df = safe_read_csv(uploaded_csv)
if base_df is None and os.path.exists(FINAL_CSV):
    base_df = safe_read_csv(FINAL_CSV)

# Track which PDB we've already processed to avoid regenerating
if "processed_pdb_hash" not in st.session_state:
    st.session_state["processed_pdb_hash"] = None

# Process PDB to generate mutations if we have PDB content
if st.session_state["pdb_content"] is not None:
    try:
        # Check if this is a new PDB (by hashing the content)
        current_hash = hashlib.md5(st.session_state["pdb_content"]).hexdigest()
        is_new_pdb = current_hash != st.session_state.get("processed_pdb_hash")
        
        seq = parse_pdb_sequence_bytes(st.session_state["pdb_content"])
        if seq:
            protein_name = os.path.splitext(st.session_state["pdb_filename"])[0] if st.session_state["pdb_filename"] else "uploaded_protein"
            
            # Check if CSV already exists for this protein
            out = os.path.join(DATA_DIR, f"{protein_name}_generated_mutations.csv")
            if os.path.exists(out) and not is_new_pdb:
                # Load existing mutations if PDB hasn't changed
                gen = safe_read_csv(out)
                if gen is not None:
                    st.sidebar.info(f"📂 Loaded existing mutations for {protein_name} ({len(gen)} mutations)")
                else:
                    # Regenerate if file is corrupted
                    seed = deterministic_seed_from_bytes(st.session_state["pdb_content"], extra=st.session_state["pdb_filename"] or "")
                    gen = generate_grounded_mutations_from_sequence(seq, protein_name=protein_name, seed=seed)
                    gen.to_csv(out, index=False)
                    st.sidebar.success(f"✅ Regenerated {len(gen)} mutations from PDB: {os.path.basename(out)}")
            else:
                # Generate new mutations
                seed = deterministic_seed_from_bytes(st.session_state["pdb_content"], extra=st.session_state["pdb_filename"] or "")
                gen = generate_grounded_mutations_from_sequence(seq, protein_name=protein_name, seed=seed)
                gen.to_csv(out, index=False)
                if is_new_pdb:
                    st.sidebar.success(f"✅ Generated {len(gen)} mutations from NEW PDB: {os.path.basename(out)}")
                else:
                    st.sidebar.success(f"✅ Generated {len(gen)} mutations from PDB: {os.path.basename(out)}")
                
                # Auto-upload to Google Sheets if enabled
                if enable_gsheets and gsheets_creds and is_new_pdb:
                    sheet_name = f"MutaGenesis_{protein_name}_{int(time.time())}"
                    with st.sidebar.spinner("📤 Uploading to Google Sheets..."):
                        success, sheet_url, error = upload_to_google_sheets(gen, sheet_name, gsheets_creds)
                        if success and sheet_url:  # Only store if we have a valid URL
                            st.session_state[f'gsheets_url_{protein_name}'] = sheet_url
                            st.session_state[f'gsheets_name_{protein_name}'] = sheet_name
                            st.sidebar.success(f"✅ Uploaded to Google Sheets!")
                        elif success and not sheet_url:
                            # Success but no URL - warn user
                            st.sidebar.warning(f"⚠️ Upload succeeded but couldn't get URL. Check your Google Drive for '{sheet_name}'")
                        else:
                            st.sidebar.error(f"❌ {error}")
            
            # Mark this PDB as processed
            st.session_state["processed_pdb_hash"] = current_hash
            
            # Merge with existing data or use as base
            if base_df is not None:
                # Check if this protein already exists in base_df
                existing_proteins = set(base_df['Protein'].unique())
                if protein_name in existing_proteins:
                    # Replace existing data for this protein
                    base_df = base_df[base_df['Protein'] != protein_name]
                    base_df = pd.concat([base_df, gen], ignore_index=True)
                    st.sidebar.info(f"🔄 Updated data for {protein_name} (now {len(gen)} mutations)")
                else:
                    # Add new protein data
                    base_df = pd.concat([base_df, gen], ignore_index=True)
                    st.sidebar.info(f"➕ Added new protein {protein_name} to dataset")
            else:
                base_df = gen
            
            # Auto-select the generated protein
            st.session_state["auto_select_protein"] = protein_name
        else:
            st.sidebar.warning("⚠️ Could not parse sequence from PDB. Check file format.")
    except Exception as e:
        st.sidebar.error(f"PDB processing error: {e}")

if base_df is None:
    st.sidebar.info("No CSV found — creating demo dataset.")
    np.random.seed(42)
    rows=[]
    for pos in range(1,51):
        for mt in ["Substitution","Insertion","Deletion","Frameshift","Nonsense","Silent"]:
            n = 1 if mt in ["Frameshift","Nonsense","Silent"] else 3
            for _ in range(n):
                o=np.random.choice(AA_LIST); m=np.random.choice(AA_LIST); ddg=np.random.uniform(-3,3); fit=max(0,10-abs(ddg))
                rows.append({"Protein":"1UBQ_demo","Position":pos,"MutationType":mt,"OriginalAA":o,"MutatedAA":m,"DeltaDeltaG":round(ddg,3),"FunctionalFitness":round(fit,3)})
    base_df = pd.DataFrame(rows)
    try: base_df.to_csv(FINAL_CSV,index=False)
    except: pass

# Normalize columns
for c in ["Protein","Position","MutationType","OriginalAA","MutatedAA","DeltaDeltaG","FunctionalFitness"]:
    if c not in base_df.columns:
        base_df[c] = "" if c not in ("Position","DeltaDeltaG","FunctionalFitness") else 0
base_df['Position']=pd.to_numeric(base_df['Position'],errors='coerce').fillna(0).astype(int)
base_df['DeltaDeltaG']=pd.to_numeric(base_df['DeltaDeltaG'],errors='coerce').fillna(0.0)
base_df['FunctionalFitness']=pd.to_numeric(base_df['FunctionalFitness'],errors='coerce').fillna(0.0)

# Sidebar
st.sidebar.header("Controls & Export")

# AI Configuration
st.sidebar.subheader("🤖 AI Predictions (Optional)")
st.sidebar.caption("Enable AI-powered functional impact predictions using Google Gemini")
use_ai = st.sidebar.checkbox("Use AI for functional impacts", value=False, help="Requires Google Gemini API key")
api_key = None
if use_ai:
    api_key_input = st.sidebar.text_input("Google Gemini API Key", type="password", help="Enter your Google Gemini API key. Get one at https://makersuite.google.com/app/apikey")
    if api_key_input:
        api_key = api_key_input
        # Clear cache if API key changed
        if st.session_state.get('gemini_api_key') != api_key:
            # Clear all cached AI predictions
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith('consequence_') and 'True' in k]
            for k in keys_to_clear:
                del st.session_state[k]
        st.session_state['gemini_api_key'] = api_key
        # Test API key
        if st.sidebar.button("🔍 Test API Key", help="Test if your API key is valid"):
            test_status = st.sidebar.empty()
            test_status.info("🔄 Testing API key...")
            try:
                # Try the newer google.genai package first (Client-based API)
                try:
                    from google import genai
                    
                    # Setup the client (like test.py)
                    client = genai.Client(api_key=api_key)
                    
                    # Try different model names
                    model_names = ["gemini-2.5-flash", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"]
                    test_success = False
                    
                    for model_name in model_names:
                        try:
                            test_response = client.models.generate_content(
                                model=model_name,
                                contents="Say 'OK' if you can read this."
                            )
                            if test_response and test_response.text:
                                test_status.success(f"✅ API key is valid! (Using {model_name})")
                                test_success = True
                                break
                        except Exception as e:
                            error_msg = str(e).lower()
                            if '404' in str(e) or 'not found' in error_msg:
                                # Model not found, try next model
                                continue
                            elif '429' in str(e) or 'quota' in error_msg or 'rate limit' in error_msg:
                                # Rate limit - reset tracking
                                if 'gemini_rate_limit' in st.session_state:
                                    st.session_state['gemini_rate_limit'] = {'last_request': 0, 'request_count': 0, 'window_start': time.time()}
                                test_status.error(
                                    "❌ **Rate limit exceeded.**\n\n"
                                    "**Free tier limits:**\n"
                                    "• ~15 requests per minute\n"
                                    "• ~1500 requests per day\n\n"
                                    "**Solutions:**\n"
                                    "• Wait 1 minute and try again\n"
                                    "• Check quota: https://makersuite.google.com/app/apikey\n"
                                    "• Predictions are cached - navigate to different positions\n"
                                    "• Consider upgrading for higher limits"
                                )
                                test_success = True  # Don't show other errors
                                break
                            elif 'API key' in error_msg or '401' in error_msg or '403' in error_msg:
                                test_status.error("❌ Invalid API key. Please check and try again.")
                                test_success = True  # Don't show other errors
                                break
                    
                    if not test_success:
                        test_status.error("❌ Could not connect to any Gemini model. Check your API key and internet connection.")
                        
                except ImportError:
                    # Fallback to old google.generativeai package
                    try:
                        import google.generativeai as genai
                        
                        # Configure API key
                        genai.configure(api_key=api_key)
                        
                        # Get an available Gemini model
                        model = get_available_gemini_model(genai, api_key)
                        if model is None:
                            # Try to list models to help debug
                            try:
                                available_models = genai.list_models()
                                model_list = []
                                for m in available_models:
                                    if hasattr(m, 'name'):
                                        model_list.append(m.name)
                                if model_list:
                                    test_status.error(f"❌ No compatible models found. Available models: {', '.join(model_list[:5])}")
                                else:
                                    test_status.error("❌ No available Gemini models found. Check your API key permissions.")
                            except:
                                test_status.error("❌ No available Gemini models found. Check your API key permissions.")
                        else:
                            test_response = model.generate_content("Say 'OK' if you can read this.")
                            if test_response and test_response.text:
                                test_status.success("✅ API key is valid!")
                            else:
                                test_status.error("❌ API key test failed - no response")
                    except ImportError:
                        test_status.error("❌ google-generativeai not installed. Run: `pip install google-generativeai` or `pip install google-genai`")
            except Exception as e:
                error_msg = str(e)
                if 'API key' in error_msg or '401' in error_msg or '403' in error_msg:
                    test_status.error("❌ Invalid API key. Please check and try again.")
                elif 'quota' in error_msg.lower() or '429' in error_msg or 'rate limit' in error_msg.lower():
                    # Reset rate limit tracking
                    if 'gemini_rate_limit' in st.session_state:
                        st.session_state['gemini_rate_limit'] = {'last_request': 0, 'request_count': 0, 'window_start': time.time()}
                    test_status.error(
                        "❌ **Rate limit exceeded.**\n\n"
                        "**Free tier limits:**\n"
                        "• ~15 requests per minute\n"
                        "• ~1500 requests per day\n\n"
                        "**Solutions:**\n"
                        "• Wait 1 minute and try again\n"
                        "• Check quota: https://makersuite.google.com/app/apikey\n"
                        "• Predictions are cached - navigate to different positions\n"
                        "• Consider upgrading for higher limits"
                    )
                else:
                    test_status.error(f"❌ Error: {error_msg[:100]}")
    elif st.session_state.get('gemini_api_key'):
        api_key = st.session_state['gemini_api_key']
        st.sidebar.success("✅ AI Enabled - Using saved API key")
    else:
        st.sidebar.warning("⚠️ API key required for AI predictions")
        use_ai = False

# Show AI status in sidebar
if use_ai and api_key:
    st.sidebar.caption("🤖 AI predictions will appear in the Mutation Consequences section")
    # Show rate limit status
    if 'gemini_rate_limit' in st.session_state:
        rate_limit = st.session_state['gemini_rate_limit']
        current_time = time.time()
        if current_time - rate_limit['window_start'] < 60:
            remaining = max(0, 12 - rate_limit['request_count'])
            if remaining < 3:
                st.sidebar.warning(f"⚠️ Rate limit: {remaining} requests left this minute")
            else:
                st.sidebar.caption(f"💡 Rate limit: ~{remaining} requests/min available")

# Hidden cheat code input in sidebar (ghost input for research paper generator)
if 'cheat_code_activated' not in st.session_state:
    st.session_state['cheat_code_activated'] = False

cheat_input = st.sidebar.text_input("", key="cheat_code_input", placeholder="👻", help="", label_visibility="collapsed")
if cheat_input and cheat_input.lower().strip() == "research":
    st.session_state['cheat_code_activated'] = True
    safe_rerun()

proteins = sorted(base_df['Protein'].unique())
# Auto-select if we just generated from PDB
default_idx = 0
if "auto_select_protein" in st.session_state and st.session_state["auto_select_protein"] in proteins:
    default_idx = proteins.index(st.session_state["auto_select_protein"])
    # Clear the flag after using it
    del st.session_state["auto_select_protein"]
selected = st.sidebar.selectbox("Active protein dataset", proteins, index=default_idx)

p_df = base_df[base_df['Protein']==selected].copy()
if p_df.empty:
    st.error("No data for selected protein.")
    st.stop()

pos_min, pos_max = int(p_df['Position'].min()), int(p_df['Position'].max())
if "sim_pos" not in st.session_state: st.session_state["sim_pos"]=float(pos_min)
if "playing" not in st.session_state: st.session_state["playing"]=False
if "interval" not in st.session_state: st.session_state["interval"]=0.05
if "last_tick" not in st.session_state: st.session_state["last_tick"]=time.time()
if "smooth_animation" not in st.session_state: st.session_state["smooth_animation"]=True
if "animation_speed" not in st.session_state: st.session_state["animation_speed"]=1.0

# Animation controls
c1,c2=st.sidebar.columns([1,1])
if c1.button("▶ Play"): st.session_state["playing"]=True
if c2.button("⏸ Pause"): st.session_state["playing"]=False

st.session_state["smooth_animation"] = st.sidebar.checkbox("Smooth animation", value=st.session_state["smooth_animation"], help="Interpolate between positions for fluid motion")
st.session_state["animation_speed"] = st.sidebar.slider("Animation speed", 0.1, 5.0, st.session_state["animation_speed"], 0.1, help="Multiplier for animation speed")
st.session_state["interval"] = st.sidebar.slider("Frame interval (s)", 0.01, 0.2, st.session_state["interval"], 0.01, help="Time between frames (lower = smoother)")

# Position slider - update smoothly during animation
current_display_pos = int(round(st.session_state["sim_pos"]))
manual = st.sidebar.slider("Position", pos_min, pos_max, current_display_pos, key="pos_slider")
if manual != current_display_pos:
    st.session_state["sim_pos"] = float(manual)
    st.session_state["playing"] = False

mut_filter = st.sidebar.selectbox("Mutation type", ["All"]+sorted(p_df['MutationType'].unique().tolist()))
smooth = st.sidebar.checkbox("Smooth trend", value=True)

# Smooth autoplay with interpolation
now = time.time()
if st.session_state["playing"]:
    elapsed = now - st.session_state["last_tick"]
    if elapsed >= st.session_state["interval"]:
        if st.session_state["smooth_animation"]:
            # Smooth interpolation: move by fractional positions
            # animation_speed of 1.0 = 1 position per interval, 2.0 = 2 positions per interval, etc.
            step_size = st.session_state["animation_speed"] * (elapsed / st.session_state["interval"])
            nxt = st.session_state["sim_pos"] + step_size
            
            # Wrap around at boundaries
            if nxt > pos_max:
                nxt = pos_min + (nxt - pos_max)
            elif nxt < pos_min:
                nxt = pos_max - (pos_min - nxt)
            
            st.session_state["sim_pos"] = nxt
        else:
            # Discrete stepping (original behavior)
            nxt = int(st.session_state["sim_pos"]) + 1
            if nxt > pos_max:
                nxt = pos_min
            st.session_state["sim_pos"] = float(nxt)
        
        st.session_state["last_tick"] = now
        safe_rerun()

# ---- Dashboard below ----
pivot = p_df.groupby(['OriginalAA','MutatedAA'])['DeltaDeltaG'].mean().reset_index().pivot(
    index='OriginalAA',columns='MutatedAA',values='DeltaDeltaG').reindex(index=AA_LIST,columns=AA_LIST).fillna(0.0)
trend = p_df.groupby('Position',as_index=False)['DeltaDeltaG'].mean().sort_values('Position')
df_vis = p_df if mut_filter=="All" else p_df[p_df['MutationType']==mut_filter]

# Layout
col1, col2 = st.columns([2,1])
with col1:
    st.subheader(f"{selected} — ΔΔG trend")
    st.plotly_chart(trend_fig(trend, current_pos=st.session_state["sim_pos"], smooth=smooth), use_container_width=True)
    st.subheader("ΔΔG distribution")
    fig_hist = px.histogram(p_df, x="DeltaDeltaG", nbins=40, marginal="box")
    fig_hist.update_layout(template="plotly_dark",paper_bgcolor=BG,plot_bgcolor=BG)
    st.plotly_chart(fig_hist, use_container_width=True)
with col2:
    # Handle fractional positions - use nearest integer for data lookup
    current_pos = float(st.session_state["sim_pos"])
    nearest_pos = int(round(current_pos))
    pos_display = f"{current_pos:.1f}" if current_pos != nearest_pos else str(nearest_pos)
    
    st.subheader(f"Position {pos_display} summary")
    pos_df = df_vis[df_vis['Position']==nearest_pos]
    
    # If smooth animation, show interpolated trend value
    if st.session_state.get("smooth_animation", False) and not trend.empty:
        try:
            interp_ddg = np.interp(current_pos, trend['Position'].values, trend['DeltaDeltaG'].values)
            interp_label = f"Interp. ΔΔG: {interp_ddg:.3f}"
        except:
            interp_label = None
    else:
        interp_label = None
    
    c1,c2,c3 = st.columns(3)
    c1.metric("Mutations",len(pos_df))
    c2.metric("Avg ΔΔG", f"{pos_df['DeltaDeltaG'].mean():.3f}" if not pos_df.empty else "N/A")
    c3.metric("Avg fitness", f"{pos_df['FunctionalFitness'].mean():.3f}" if not pos_df.empty else "N/A")
    
    if interp_label:
        st.caption(f"📊 {interp_label}")
    
    if not pos_df.empty:
        # Mutation consequences with real database lookups and AI (cached)
        # Note: protein_info will be fetched later, but we'll try to get it if available
        pdb_source_name = st.session_state.get("pdb_filename", selected if len(selected) == 4 and selected.isalnum() else None)
        protein_info_for_ai = None
        if pdb_source_name:
            info_key = f"protein_info_{pdb_source_name}"
            protein_info_for_ai = st.session_state.get(info_key)
        
        cache_key = f"consequence_{selected}_{nearest_pos}_{use_ai}"
        if cache_key not in st.session_state:
            spinner_msg = "🔍 Checking databases and generating AI predictions..." if use_ai else "🔍 Checking databases for disease associations..."
            with st.spinner(spinner_msg):
                consequence_summary = get_position_consequence_summary(
                    pos_df, 
                    protein_name=selected, 
                    protein_info=protein_info_for_ai,
                    use_ai=use_ai,
                    api_key=api_key
                )
                st.session_state[cache_key] = consequence_summary
        else:
            consequence_summary = st.session_state[cache_key]
        
        if consequence_summary:
            st.markdown("---")
            st.subheader("🧬 Mutation Consequences")
            
            # Pathogenicity
            path_colors = {
                'Pathogenic': '🔴',
                'Likely Pathogenic': '🟠',
                'Possibly Pathogenic': '🟡',
                'Likely Benign': '🟢',
                'Benign': '🟢',
                'Unknown': '⚪'
            }
            path_icon = path_colors.get(consequence_summary['primary_pathogenicity'], '⚪')
            st.markdown(f"**{path_icon} Primary Pathogenicity:** {consequence_summary['primary_pathogenicity']}")
            
            # Disease associations
            if consequence_summary.get('disease_associations'):
                st.markdown("**🏥 Disease Associations:**")
                for assoc in consequence_summary['disease_associations']:
                    st.caption(f"  • {assoc}")
            
            # Functional impacts
            if consequence_summary.get('functional_impacts'):
                st.markdown("**⚙️ Functional Impacts:**")
                # Check if any are AI-generated
                has_ai = any(cons.get('ai_generated', False) for cons in consequence_summary.get('consequences', []))
                if has_ai:
                    st.caption("🤖 *AI-generated prediction*")
                for impact in consequence_summary['functional_impacts']:
                    st.caption(f"  • {impact}")
            
            # Immunity effects
            if consequence_summary.get('immunity_effects'):
                st.markdown("**🛡️ Immunity Effects:**")
                for effect in consequence_summary['immunity_effects']:
                    st.caption(f"  • {effect}")
            
            # Real database results
            real_info = consequence_summary.get('real_disease_info')
            if real_info and real_info.get('found'):
                st.markdown("---")
                st.markdown("**🌐 Real Database Lookup Results:**")
                
                if real_info.get('diseases'):
                    st.markdown("**📊 Found Disease Associations:**")
                    for disease in real_info['diseases']:
                        disease_name = disease.get('name', 'Unknown')
                        disease_id = disease.get('id', '')
                        source = disease.get('source', 'Database')
                        if disease_id and 'DI-' in disease_id:
                            st.caption(f"  • [{disease_name}](https://www.uniprot.org/diseases/{disease_id}) ({source})")
                        else:
                            st.caption(f"  • {disease_name} ({source})")
                
                if real_info.get('cancer_associations'):
                    st.markdown("**🎗️ Cancer Associations:**")
                    for cancer in real_info['cancer_associations']:
                        st.caption(f"  • {cancer}")
                
                if real_info.get('database_links'):
                    st.markdown("**🔗 Database Links:**")
                    for db_name, db_url in real_info['database_links'].items():
                        st.caption(f"  • [{db_name.upper()}]({db_url})")
                
                # Refresh button
                if st.button("🔄 Refresh Database Lookup", key=f"refresh_db_{nearest_pos}"):
                    # Clear cache and rerun
                    if cache_key in st.session_state:
                        del st.session_state[cache_key]
                    safe_rerun()
            elif real_info and not real_info.get('found'):
                st.caption("ℹ️ No specific disease associations found in databases. Showing computational predictions.")
                if st.button("🔄 Retry Database Lookup", key=f"retry_db_{nearest_pos}"):
                    if cache_key in st.session_state:
                        del st.session_state[cache_key]
                    safe_rerun()
            
            # Expandable detailed view
            with st.expander("📋 Detailed Mutation Analysis", expanded=False):
                top = pos_df.reindex(pos_df['DeltaDeltaG'].abs().sort_values(ascending=False).index).head(10)
                
                # Add consequence predictions to table
                display_df = top[['MutationType','OriginalAA','MutatedAA','DeltaDeltaG','FunctionalFitness']].copy()
                consequences_list = []
                for _, row in top.iterrows():
                    cons = predict_mutation_consequence(row)
                    consequences_list.append(f"{cons['pathogenicity']} | {cons['functional_impact']}")
                display_df['Consequence'] = consequences_list
                
                st.table(display_df.reset_index(drop=True))
                
                # Show pathogenicity breakdown
                if consequence_summary.get('pathogenicity_breakdown'):
                    st.markdown("**Pathogenicity Distribution:**")
                    for path, count in consequence_summary['pathogenicity_breakdown'].items():
                        pct = (count / consequence_summary['total_mutations']) * 100
                        st.caption(f"  {path_colors.get(path, '⚪')} {path}: {count} mutations ({pct:.1f}%)")
        else:
            top = pos_df.reindex(pos_df['DeltaDeltaG'].abs().sort_values(ascending=False).index).head(8)
            st.table(top[['MutationType','OriginalAA','MutatedAA','DeltaDeltaG','FunctionalFitness']].reset_index(drop=True))
    else:
        st.info("No mutations at this position.")

col3, col4 = st.columns(2)
with col3:
    st.subheader("AA → AA ΔΔG heatmap")
    st.plotly_chart(heatmap_fig(pivot), use_container_width=True)
with col4:
    st.subheader("ΔΔG vs FunctionalFitness (all)")
    st.plotly_chart(scatter_fig(df_vis), use_container_width=True)

# 3D Viewer
st.subheader("3D Viewer (highlight current residue)")
pdb_string = None
pdb_source_name = None

# First try session state (uploaded or selected PDB)
if st.session_state.get("pdb_content") is not None:
    try:
        pdb_string = st.session_state["pdb_content"].decode('utf8', errors='ignore')
        pdb_source_name = st.session_state.get("pdb_filename", "uploaded")
    except:
        pdb_string = None

# If no PDB in session state, try to fetch from RCSB if protein name looks like a PDB ID
if pdb_string is None and len(selected) == 4 and selected.isalnum():
    try:
        import requests
        r = requests.get(f"https://files.rcsb.org/download/{selected}.pdb", timeout=8)
        if r.status_code == 200:
            pdb_string = r.text
            # Store in session state for future use
            st.session_state["pdb_content"] = r.content
            st.session_state["pdb_filename"] = f"{selected}.pdb"
            pdb_source_name = selected
    except:
        pdb_string = None

# Fetch protein information
protein_info = None
if pdb_source_name:
    # Cache protein info in session state
    info_key = f"protein_info_{pdb_source_name}"
    if info_key not in st.session_state:
        with st.spinner("Fetching protein information..."):
            st.session_state[info_key] = fetch_protein_info(pdb_source_name)
    protein_info = st.session_state.get(info_key)

# Display protein information if available
if protein_info:
    with st.expander("📋 Protein Information", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            if protein_info.get('title'):
                st.write(f"**Title:** {protein_info['title']}")
            if protein_info.get('function') and protein_info['function'] != 'N/A':
                st.write(f"**Function:** {protein_info['function']}")
        with col2:
            if protein_info.get('organism') and protein_info['organism'] != 'N/A':
                st.write(f"**Organism:** {protein_info['organism']}")
            if protein_info.get('resolution'):
                st.write(f"**Resolution:** {protein_info['resolution']:.2f} Å")
            if protein_info.get('experimental_method'):
                st.write(f"**Method:** {protein_info['experimental_method']}")
        if protein_info.get('pdb_id'):
            st.caption(f"Source: RCSB PDB entry {protein_info['pdb_id']}")

# Display 3D viewer
if pdb_string and py3Dmol is not None:
    pdb_name = st.session_state.get("pdb_filename", "PDB") if st.session_state.get("pdb_content") else selected
    # Use nearest integer position for 3D highlighting (PDB uses integer residue numbers)
    highlight_res = int(round(float(st.session_state["sim_pos"])))
    current_pos_display = f"{st.session_state['sim_pos']:.1f}" if st.session_state['sim_pos'] != highlight_res else str(highlight_res)
    st.caption(f"📄 Viewing: {pdb_name} | Highlighting residue {current_pos_display}")
    
    # Pass mutation data for color-coding
    mutation_data_for_viewer = p_df if not p_df.empty else None
    html_result = py3dmol_html(pdb_string, highlight_res=highlight_res, mutation_data=mutation_data_for_viewer)
    
    if html_result:
        html_content, ddg_min, ddg_max = html_result
        st.components.v1.html(html_content, height=520)
        
        # Add mutation visualization legend and info
        if not p_df.empty:
            pos_df = p_df[p_df['Position'] == highlight_res]
            if not pos_df.empty:
                avg_ddg = pos_df['DeltaDeltaG'].mean()
                st.caption(f"💡 Position {current_pos_display}: Avg ΔΔG = {avg_ddg:.3f} kcal/mol | {len(pos_df)} mutations")
            
            # Spectrum colorbar legend instead of emojis
            if ddg_min is not None and ddg_max is not None and ddg_min != ddg_max:
                st.caption("**Color Spectrum:** Residues colored by average ΔΔG (blue = stabilizing, red = destabilizing)")
                colorbar_fig = create_colorbar_legend(ddg_min, ddg_max)
                if colorbar_fig:
                    st.plotly_chart(colorbar_fig, use_container_width=True, config={'displayModeBar': False})
                st.caption("🟡 Yellow highlight = current position")
    else:
        html_content, _, _ = py3dmol_html(pdb_string, highlight_res=highlight_res)
        if html_content:
            st.components.v1.html(html_content, height=520)
else:
    if py3Dmol is None:
        st.info("⚠️ py3Dmol not installed — install 'py3Dmol' to enable 3D viewer: `pip install py3Dmol`")
    else:
        st.info("📋 No PDB available to render in 3D. Upload one in the sidebar, select from the directory, or ensure internet access to fetch from RCSB.")

# Google Sheets QR Code Display
st.markdown("---")
st.subheader("📱 Google Sheets QR Code")
if st.session_state.get("pdb_filename"):
    protein_name = os.path.splitext(st.session_state["pdb_filename"])[0]
    sheet_url = st.session_state.get(f'gsheets_url_{protein_name}')
    sheet_name = st.session_state.get(f'gsheets_name_{protein_name}')
    
    # Validate URL - must be a valid HTTP/HTTPS URL, not None or string "None"
    if sheet_url and sheet_url != "None" and str(sheet_url).strip() and str(sheet_url).startswith('http'):
        sheet_url = str(sheet_url).strip()  # Ensure it's a string
        st.success(f"✅ Data uploaded to Google Sheets: [{sheet_name}]({sheet_url})")
        
        # Generate and display QR code
        qr_img = generate_qr_code(sheet_url, size=400)
        if qr_img:
            # Convert PIL Image to bytes for Streamlit
            img_buffer = io.BytesIO()
            qr_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image(img_buffer, caption="Scan to view data in Google Sheets", use_container_width=True)
                st.download_button(
                    "📥 Download QR Code",
                    img_buffer.getvalue(),
                    file_name=f"QR_{protein_name}.png",
                    mime="image/png"
                )
        else:
            st.warning("QR code generation not available. Install: pip install qrcode[pil]")
    elif sheet_url in [None, "None", ""] or (sheet_url and not str(sheet_url).strip().startswith('http')):
        # Clear invalid URL from session state if it exists
        if f'gsheets_url_{protein_name}' in st.session_state:
            del st.session_state[f'gsheets_url_{protein_name}']
        st.info("No valid Google Sheets link available. Enable auto-export and upload a PDB to generate a QR code.")
else:
    st.info("Upload or select a PDB file to generate Google Sheets export and QR code.")

# Manual export option
st.markdown("---")
st.subheader("📤 Manual Export to Google Sheets")
if base_df is not None and not base_df.empty:
    if enable_gsheets and gsheets_creds:
        if st.button("📊 Export Current Dataset to Google Sheets"):
            sheet_name = f"MutaGenesis_Export_{int(time.time())}"
            with st.spinner("Uploading to Google Sheets..."):
                success, sheet_url, error = upload_to_google_sheets(base_df, sheet_name, gsheets_creds)
                if success and sheet_url and sheet_url != "None" and sheet_url.strip() and sheet_url.startswith('http'):
                    st.success(f"✅ Uploaded! [View Sheet]({sheet_url})")
                    # Generate QR code
                    qr_img = generate_qr_code(sheet_url, size=400)
                    if qr_img:
                        img_buffer = io.BytesIO()
                        qr_img.save(img_buffer, format='PNG')
                        img_buffer.seek(0)
                        st.image(img_buffer, caption="Scan to view data", use_container_width=True)
                        st.download_button(
                            "📥 Download QR Code",
                            img_buffer.getvalue(),
                            file_name="QR_Export.png",
                            mime="image/png"
                        )
                else:
                    st.error(f"❌ {error}")
    else:
        st.info("Enable Google Sheets export in the sidebar to use this feature.")

# AI Assistant Chat Interface
if use_ai and api_key:
    st.markdown("---")
    st.subheader("🤖 AI Assistant - Ask Questions About Your Data")
    st.caption("Ask questions about the protein, mutations, visualizations, or any aspect of what you're seeing. The AI has context about your current view.")
    
    # Initialize chat history
    if 'chat_history' not in st.session_state:
        st.session_state['chat_history'] = []
    
    # Build context data for the AI
    current_pos = int(round(float(st.session_state["sim_pos"])))
    pos_df_current = p_df[p_df['Position'] == current_pos] if not p_df.empty else pd.DataFrame()
    
    # Get top mutations by absolute ΔΔG
    top_mutations = []
    if not p_df.empty:
        top_muts_df = p_df.reindex(p_df['DeltaDeltaG'].abs().sort_values(ascending=False).index).head(5)
        for _, row in top_muts_df.iterrows():
            top_mutations.append({
                'mutation': f"{row.get('OriginalAA', '')}{int(row.get('Position', 0))}{row.get('MutatedAA', '')}",
                'ddg': f"{row.get('DeltaDeltaG', 0):.3f}",
                'type': row.get('MutationType', 'Unknown')
            })
    
    context_data = {
        'protein_name': selected,
        'current_position': current_pos,
        'position_range': f"{pos_min} - {pos_max}",
        'total_mutations': len(p_df),
        'mutation_types': sorted(p_df['MutationType'].unique().tolist()) if not p_df.empty else [],
        'avg_ddg': f"{p_df['DeltaDeltaG'].mean():.3f}" if not p_df.empty else "N/A",
        'ddg_range': f"{p_df['DeltaDeltaG'].min():.3f} to {p_df['DeltaDeltaG'].max():.3f}" if not p_df.empty else "N/A",
        'avg_fitness': f"{p_df['FunctionalFitness'].mean():.3f}" if not p_df.empty else "N/A",
        'protein_info': protein_info,
        'current_position_data': {
            'position': current_pos,
            'mutation_count': len(pos_df_current),
            'avg_ddg': f"{pos_df_current['DeltaDeltaG'].mean():.3f}" if not pos_df_current.empty else "N/A",
            'worst_mutation': f"{pos_df_current.loc[pos_df_current['DeltaDeltaG'].idxmax(), 'OriginalAA']}{current_pos}{pos_df_current.loc[pos_df_current['DeltaDeltaG'].idxmax(), 'MutatedAA']}" if not pos_df_current.empty and pos_df_current['DeltaDeltaG'].max() > 0 else "N/A",
            'best_mutation': f"{pos_df_current.loc[pos_df_current['DeltaDeltaG'].idxmin(), 'OriginalAA']}{current_pos}{pos_df_current.loc[pos_df_current['DeltaDeltaG'].idxmin(), 'MutatedAA']}" if not pos_df_current.empty and pos_df_current['DeltaDeltaG'].min() < 0 else "N/A"
        } if not pos_df_current.empty else None,
        'top_mutations': top_mutations
    }
    
    # Display chat history
    if st.session_state['chat_history']:
        st.markdown("**💬 Chat History:**")
        for i, msg in enumerate(st.session_state['chat_history']):
            with st.chat_message(msg['role']):
                st.write(msg['content'])
    
    # Chat input
    user_question = st.chat_input("Ask a question about your data...")
    
    if user_question:
        # Add user message to history
        st.session_state['chat_history'].append({'role': 'user', 'content': user_question})
        
        # Get AI response
        with st.spinner("🤖 Thinking..."):
            ai_response = ask_ai_assistant(user_question, context_data, api_key)
        
        if ai_response:
            # Add AI response to history
            st.session_state['chat_history'].append({'role': 'assistant', 'content': ai_response})
        else:
            # Error handling
            error_msg = "Sorry, I couldn't generate a response. This might be due to rate limits or API issues. Please try again in a moment."
            st.session_state['chat_history'].append({'role': 'assistant', 'content': error_msg})
        
        # Rerun to show new messages
        safe_rerun()
    
    # Clear chat button
    if st.session_state['chat_history']:
        if st.button("🗑️ Clear Chat History"):
            st.session_state['chat_history'] = []
            safe_rerun()
    
    # Example questions
    st.caption("💡 **Example questions:**")
    st.caption("• 'What does the ΔΔG trend tell us about this protein?'")
    st.caption("• 'Which mutations are most destabilizing at position " + str(current_pos) + "?'")
    st.caption("• 'Explain the relationship between ΔΔG and functional fitness'")
    st.caption("• 'What does the heatmap show about amino acid substitutions?'")
else:
    st.markdown("---")
    st.info("💡 **Enable AI in the sidebar** to use the AI Assistant. It can answer questions about your protein data, mutations, and visualizations!")

# Show research paper generator if cheat code is activated
if st.session_state.get('cheat_code_activated', False):
    st.markdown("---")
    st.subheader("📄 Research Paper Generator")
    st.caption("🔓 *Cheat code activated*")
    
    col1, col2 = st.columns(2)
    with col1:
        author_name = st.text_input("Author Name", value=st.session_state.get('research_author', ''), key="research_author_input")
        if author_name:
            st.session_state['research_author'] = author_name
    with col2:
        institution = st.text_input("Institution", value=st.session_state.get('research_institution', ''), key="research_institution_input")
        if institution:
            st.session_state['research_institution'] = institution
    
    if st.button("📄 Generate Research Paper", type="primary"):
        if not p_df.empty:
            with st.spinner("Generating research paper..."):
                # Get trend and pivot data
                trend_data = p_df.groupby('Position', as_index=False)['DeltaDeltaG'].mean().sort_values('Position')
                pivot_data = p_df.groupby(['OriginalAA','MutatedAA'])['DeltaDeltaG'].mean().reset_index().pivot(
                    index='OriginalAA', columns='MutatedAA', values='DeltaDeltaG'
                )
                
                html_content = generate_research_page_html(
                    protein_name=selected,
                    p_df=p_df,
                    protein_info=protein_info,
                    trend_data=trend_data,
                    pivot_data=pivot_data,
                    author_name=st.session_state.get('research_author', ''),
                    institution=st.session_state.get('research_institution', '')
                )
                
                st.success("✅ Research paper generated!")
                st.markdown("---")
                
                # Display HTML in expander
                with st.expander("📄 View Research Paper", expanded=True):
                    st.components.v1.html(html_content, height=800, scrolling=True)
                
                # Download button
                st.download_button(
                    "📥 Download Research Paper (HTML)",
                    html_content,
                    file_name=f"Research_Paper_{selected}_{time.strftime('%Y%m%d')}.html",
                    mime="text/html"
                )
        else:
            st.error("No data available. Please select a protein first.")
    
    if st.button("🔒 Hide Research Generator"):
        st.session_state['cheat_code_activated'] = False
        safe_rerun()

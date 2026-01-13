Mutagenesis Intelligence System (MIS)

A Computational Study on Protein Stability and Pathogenicity

🔬 Science Fair Context

Research Question: To what degree does the chemical nature and disruption level of a mutation correlate with the loss of functional fitness in a protein structure?
Hypothesis: "More disruptive mutations—specifically high-energy substitutions (∆∆G > 2.0 kcal/mol), frameshifts, and nonsense mutations—lead to lower functional fitness due to significant structural destabilization and premature truncation of the polypeptide chain."
Project Goal: To bridge the gap between raw genomic data and structural biology by creating an interactive, AI-enhanced dashboard that predicts the health of a protein after genetic interference.

🛠 Methodology (The Variable Framework)

Variables

Independent Variable: Mutation Disruption Level (Categorized as Low: Silent/Conservative, or High: Frameshift/Nonsense).
Dependent Variable: Functional Fitness Score (Numerical scale from 0.0 to 10.0) and ∆∆G (Thermodynamic stability delta).
Control Variables: Protein backbone architecture (PDB coordinates), physiological simulation parameters, and deterministic seed values for mutation generation.

Materials

Software: Python 3.9+, Streamlit (UI Framework), Plotly (Data Viz), py3Dmol (Molecular Rendering).
Hardware: Personal Computer with GPU acceleration for 3D rendering.
Data Sources: RCSB Protein Data Bank (PDB), UniProt Knowledgebase, and ClinVar.
AI Engine: Google Gemini API for automated functional impact analysis.

🚀 Key Features

1. 3D Molecular Visualization
The program renders an interactive 3D model of the protein. Residues are color-coded based on their $\Delta\Delta G$ values, allowing for immediate visual identification of "instability hotspots."

2. Thermodynamic Analysis (∆∆G)
MIS calculates the change in Gibbs free energy. Positive values indicate destabilization (red spectrum), while negative values indicate stabilization (blue spectrum).

3. AA → AA Heatmaps
A substitution matrix that tracks the fitness cost of swapping any amino acid for another. This reveals the "chemical tolerance" of the protein sequence.

4. AI Assistant & Predictive Analytics
Integrated AI analyzes current view context to explain complex biological interactions. It classifies mutations as "Pathogenic" or "Benign" based on ACMG clinical guidelines.

5. Export & Sharing Suite
Generates automated Google Sheets exports and QR codes, allowing judges to scan and view live data on their own mobile devices.

💻 Installation & Usage
Clone the environment: Ensure Python is installed.

Install dependencies:
pip install streamlit pandas numpy plotly scipy py3Dmol google-genai gspread qrcode[pil]

Run the app:
streamlit run app.py

📜 Conclusion

The MIS proves that computational modeling can effectively predict biological outcomes. By quantifying "disruption" through thermodynamics and fitness scores, we can identify which genetic changes are most likely to lead to disease before conducting expensive "wet-lab" experiments.

Author: Rock
Category: Computational Biology / Bioinformatics
Date: January 2026

Category: Computational Biology / Bioinformatics

Date: January 2026

# Google Gemini API Setup Guide

## Overview
The Mutagenesis Intelligence System uses Google's Gemini API for AI-powered functional impact predictions. This guide will help you set up your Gemini API key.

## Getting Your Gemini API Key

### Step 1: Visit Google AI Studio
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account

### Step 2: Create API Key
1. Click "Create API Key" or "Get API Key"
2. If prompted, create a new Google Cloud project (or select an existing one)
3. Your API key will be displayed - **copy it immediately** (you won't be able to see it again)

### Step 3: Configure in the App
1. In the Mutagenesis app sidebar:
   - Check "Use AI for functional impacts"
   - Paste your Gemini API key in the password field
   - The key will be saved for your session

## Features

### AI-Powered Predictions
- Uses Google's Gemini Pro model
- Generates context-aware functional impact predictions
- Considers protein structure, mutation type, ΔΔG values, and functional fitness
- Provides scientific, mechanistic insights

### Cost
- Google Gemini API offers a free tier with generous limits
- Check current pricing at [Google AI Studio](https://makersuite.google.com/app/apikey)

## Troubleshooting

### "google-generativeai library not installed"
Run: `pip install google-generativeai`

**Note:** The app uses `google-generativeai` (the stable API). While Google has a newer `google-genai` package, it uses a different API structure. The app is configured to use `google-generativeai` for compatibility and stability.

### "API key required for AI predictions"
- Make sure you've entered a valid Gemini API key
- Check that the key hasn't expired or been revoked
- Verify you copied the entire key (no extra spaces)

### "Error generating AI prediction"
- Check your internet connection
- Verify the API key is correct
- Check if you've exceeded API rate limits
- The system will automatically fall back to preset predictions if AI fails

## Security Notes
- Keep your API key secure and don't share it publicly
- The key is stored in session state (temporary, cleared when app closes)
- For production use, consider using environment variables

## Example Usage
1. Enable "Use AI for functional impacts" in sidebar
2. Enter your Gemini API key
3. Navigate to any position with mutations
4. View AI-generated functional impact predictions
5. Look for the "🤖 AI-generated prediction" indicator

## Benefits of Gemini
- **Free tier available** - Great for testing and small projects
- **Fast responses** - Optimized for quick predictions
- **Scientific accuracy** - Trained on scientific literature
- **Cost-effective** - More affordable than some alternatives


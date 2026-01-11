# Multilingual Support & Medical Recommendations Setup

## Features Implemented

### 1. Multilingual Support
- **Languages Supported**: English, Hindi, Bengali, Telugu, Marathi, Tamil, Gujarati, Kannada, Malayalam, Odia, Punjabi
- **i18n Library**: react-i18next with browser language detection
- **Language Switcher**: Available in the header on all pages
- **Translation Files**: Located in `src/i18n/locales/`

### 2. Dynamic Medical Recommendations
- **Severity-Based Recommendations**: 
  - Critical: Immediate medical attention, emergency services contact
  - Moderate: Doctor consultation within 24-48 hours, monitoring guidelines
  - Mild: Home care recommendations, basic hygiene practices
- **Disease-Specific Recommendations**: Additional recommendations based on diagnosis (Dengue, Malaria, Typhoid, etc.)

### 3. Hospital Finder with Google Maps
- **Automatic Detection**: Shows nearby hospitals for critical severity cases
- **Features**:
  - Distance calculation
  - Phone numbers (when available)
  - Get directions via Google Maps
  - Call hospital directly
- **Fallback**: Uses mock data when Google Maps API key is not configured

## Setup Instructions

### Google Maps API (Optional)
To enable real hospital search:

1. Get a Google Maps API key from [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the following APIs:
   - Places API
   - Geocoding API
   - Maps JavaScript API
3. Add to your `.env` file:
   ```
   VITE_GOOGLE_MAPS_API_KEY=your_api_key_here
   ```
4. Add Google Maps script to `index.html` (optional, for Places API):
   ```html
   <script src="https://maps.googleapis.com/maps/api/js?key=YOUR_API_KEY&libraries=places"></script>
   ```

**Note**: The app works without Google Maps API key using mock hospital data for demonstration.

### Language Files
Translation files are in `src/i18n/locales/`. To add more languages:
1. Create a new JSON file (e.g., `as.json` for Assamese)
2. Copy structure from `en.json`
3. Translate all values
4. Add to `src/i18n/config.ts`

## Usage

### Using Translations in Components
```tsx
import { useTranslation } from 'react-i18next';

const MyComponent = () => {
  const { t } = useTranslation();
  return <h1>{t('home.title')}</h1>;
};
```

### Language Switcher
The language switcher is automatically available in the header. Users can:
- Select from 11 Indian languages
- Language preference is saved in localStorage
- Automatically detects browser language on first visit

## Medical Recommendations Logic

Recommendations are dynamically generated based on:
1. **Severity Level**: Critical, Moderate, or Mild
2. **Disease Type**: Dengue, Malaria, Typhoid, Viral Fever, etc.
3. **Lab Values**: Platelet count, WBC, RBC abnormalities
4. **Symptoms**: Number and type of symptoms

For critical cases, the HospitalFinder component automatically:
- Requests user location (with permission)
- Searches for nearby hospitals within 10km
- Displays top 3 hospitals with contact info
- Provides navigation links


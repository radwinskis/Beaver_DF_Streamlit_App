import streamlit as st
import ee
import folium
from folium import plugins
from streamlit_folium import st_folium
import json
from google.oauth2 import service_account
import os

# =================================================================
# 1. Page Config & Authentication
# =================================================================
st.set_page_config(page_title="Beaver Debris Flow Analysis", layout="wide")

try:
    # 1. Get the raw string from secrets
    key_content = st.secrets["textkey"]
    
    # 2. Parse JSON with 'strict=False'
    key_dict = json.loads(key_content, strict=False)
    
    # 3. Define the mandatory Earth Engine Scope
    scopes = ['https://www.googleapis.com/auth/earthengine']
    
    # 4. Create Credentials WITH Scopes
    credentials = service_account.Credentials.from_service_account_info(
        key_dict, 
        scopes=scopes
    )
    
    # 5. Initialize
    ee.Initialize(credentials=credentials)
    
except Exception as e:
    # Fallback for Local Development
    local_key_path = 'C:\\Users\\mradwin\\ut-gee-ugs-bsf-dev-53dcc5d729e0.json'
    
    if os.path.exists(local_key_path):
        credentials = ee.ServiceAccountCredentials(
            'localpythonscripts@ut-gee-ugs-bsf-dev.iam.gserviceaccount.com', 
            local_key_path
        )
        ee.Initialize(credentials=credentials)
    else:
        st.error("🚨 Authentication Error")
        st.code(f"Detailed Error: {e}")
        st.stop()

# =================================================================
# Custom Folium Earth Engine Helper
# =================================================================
def add_ee_layer(self, ee_image_object, vis_params, name, show=True, opacity=1.0):
    """Adds a Google Earth Engine image to a Folium map."""
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data &copy; Google Earth Engine',
        name=name,
        show=show,
        opacity=opacity,
        overlay=True,
        control=True
    ).add_to(self)

# Bind the helper function to Folium's Map class
folium.Map.add_ee_layer = add_ee_layer

# =================================================================
# 2. Define Assets & Palettes
# =================================================================
@st.cache_data
def get_assets():
    ag = ee.FeatureCollection('projects/ut-gee-ugs-bsf-dev/assets/WRLU_4326_LU_Group') \
        .filter(ee.Filter.eq('LU_Group', 'Active IR')) \
        .filter(ee.Filter.eq('IRR_Method', 'Sprinkler'))
    
    map_bounds = ee.Geometry.Polygon(
        [[[-112.834396, 38.173433], 
          [-112.834396, 38.375577], 
          [-112.449188, 38.375577], 
          [-112.449188, 38.173433], 
          [-112.834396, 38.173433]]])
          
    # Style the roads for Folium (converting FeatureCollection to a painted image)
    roads_fc = ee.FeatureCollection("TIGER/2016/Roads").filterBounds(map_bounds)
    roads_styled = roads_fc.style(color='white', width=1)
    
    before = ee.Image("projects/ut-gee-ugs-bsf-dev/assets/Beaver_Debris_Flow_Jul_2026/Before_Debris_Flow")
    after = ee.Image("projects/ut-gee-ugs-bsf-dev/assets/Beaver_Debris_Flow_Jul_2026/After_Debris_Flow")
    diffClass = ee.Image("projects/ut-gee-ugs-bsf-dev/assets/Beaver_Debris_Flow_Jul_2026/Index_Difference_Classifications")
    diffClassMasked = ee.Image("projects/ut-gee-ugs-bsf-dev/assets/Beaver_Debris_Flow_Jul_2026/difference_images_merged")
    summaryChange = ee.Image("projects/ut-gee-ugs-bsf-dev/assets/Beaver_Debris_Flow_Jul_2026/Summary_of_Changes_Image_Merged")
    
    # Binary mask: 0 inside ag fields, 1 everywhere else
    not_ag_mask = ee.Image.constant(1).paint(ag, 0)
    
    return not_ag_mask, roads_styled, before, after, diffClass, diffClassMasked, summaryChange

not_ag_mask, roads_styled, before, after, diffClass, diffClassMasked, summaryChange = get_assets()

# Palettes
rdbu = ['red', 'white', 'blue']
black_red = ['black', 'red']
inferno = ['#000004', '#20114B', '#57157E', '#8F0DA4', '#C93681', '#F7705C', '#FDC926', '#FCFFA4']
agreement_palette = ['white', 'yellow', 'orange', 'red']

# =================================================================
# 3. Sidebar UI & Logic
# =================================================================
st.sidebar.title('Beaver Debris Flow Analysis')
st.sidebar.markdown("#### Made by Mark Radwin, Geologist, PhD/PG at the Utah Geological Survey")
st.sidebar.markdown("###### Use this sidebar to select viewing mode and bands to visualize. You may need to reload the page or re-choose an option for the map to update.")

# Mask Checkbox
mask_ag = st.sidebar.checkbox('Exclude Agricultural Fields (Mask)', value=True)

def apply_mask(image):
    """Applies the Ag mask if the checkbox is checked."""
    return image.updateMask(not_ag_mask) if mask_ag else image

# Separator
st.sidebar.markdown("---")
st.sidebar.subheader("Viewing Mode")

mode = st.sidebar.radio("Select a viewing mode:", [
    '1. Compare Before & After (Swipe)', 
    '2. View Change Metrics (Single Map)', 
    '3. View Change Boundaries (Single Map)'
])

# Initialize Map
m = folium.Map(location=[38.274, -112.641], zoom_start=12)
# st_folium(m, use_container_width=True, height=800)

# ---------------------------------------------
# MODE 1: SWIPE
# ---------------------------------------------
if '1.' in mode:
    swipe_options = {
        'True Color': {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 0.4},
        'Albedo': {'band': 'albedo', 'min': 0.1, 'max': 0.35, 'palette': inferno},
        'NDVI (Vegetation Index)': {'band': 'ndvi', 'min': -0.2, 'max': 0.8, 'palette': ['white', 'green']},
        'NDMI (Moisture Index)': {'band': 'ndmi', 'min': -0.1, 'max': 0.5, 'palette': inferno},
        'SAVI (Vegetation Index)': {'band': 'savi', 'min': -0.1, 'max': 0.5, 'palette': ['white', 'green']},
        'C-band SAR Backscatter (dB)': {'band': 'VV', 'min': -15, 'max': 0, 'palette': inferno}
    }
    
    choice = st.sidebar.selectbox('Select bands to compare (Before left, After right):', list(swipe_options.keys()))
    params = swipe_options[choice]
    
    if choice == 'True Color':
        left_img = apply_mask(before)
        right_img = apply_mask(after)
        vis = params
    else:
        left_img = apply_mask(before.select(params['band']))
        right_img = apply_mask(after.select(params['band']))
        vis = {'min': params['min'], 'max': params['max'], 'palette': params['palette']}

    # Get Earth Engine Map IDs
    left_map_id = left_img.getMapId(vis)
    right_map_id = right_img.getMapId(vis)
    
    # Create individual Folium Tile Layers
    left_layer = folium.raster_layers.TileLayer(
        tiles=left_map_id['tile_fetcher'].url_format,
        attr='Google Earth Engine',
        name=f'Before {choice}',
        overlay=True
    ).add_to(m)
    
    right_layer = folium.raster_layers.TileLayer(
        tiles=right_map_id['tile_fetcher'].url_format,
        attr='Google Earth Engine',
        name=f'After {choice}',
        overlay=True
    ).add_to(m)
    
    # Add Folium swipe plugin
    plugins.SideBySideLayers(left_layer, right_layer).add_to(m)
    
    # Add roads globally to the map on top of the swipe layer
    m.add_ee_layer(roads_styled, {}, 'Roads', True, 0.6)
    # st_folium(m, use_container_width=True, height=800, returned_objects=[])

# ---------------------------------------------
# MODE 2: METRICS
# ---------------------------------------------
# elif '2.' in mode:
    
#     m.add_ee_layer(apply_mask(after), {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 0.35}, 'After True Color')
    
#     metric_type = st.sidebar.selectbox('Select metric classification type:', [
#         'Unclassified Change Metrics (Raw Differences)', 
#         'Classified Change Metrics (Boundaries)'
#     ])
    
#     st.sidebar.caption('Use the layers button ⧉ in the map (top right) to toggle specific bands.')
    
#     if 'Unclassified' in metric_type:
#         img = apply_mask(diffClassMasked)
#         m.add_ee_layer(img.select('albedo_difference'), {'min': -0.2, 'max': 0.2, 'palette': rdbu}, 'albedo difference', True)
#         m.add_ee_layer(img.select('ndvi_difference'), {'min': -0.2, 'max': 0.2, 'palette': rdbu}, 'ndvi difference', False)
#         m.add_ee_layer(img.select('ndmi_difference'), {'min': -0.2, 'max': 0.2, 'palette': rdbu}, 'ndmi difference', False)
#         m.add_ee_layer(img.select('savi_difference'), {'min': -0.2, 'max': 0.2, 'palette': rdbu}, 'savi difference', False)
#         m.add_ee_layer(img.select('SAR_difference_VV'), {'min': -10, 'max': 10, 'palette': rdbu}, 'Sentinel-1 VV difference', False)
        
#         # Streamlit-native Legend
#         st.sidebar.markdown("### Difference (RdBu Scale)")
#         st.sidebar.markdown("<div style='background: linear-gradient(to right, red, white, blue); height: 15px; border-radius: 5px;'></div>", unsafe_allow_html=True)
#         st.sidebar.markdown("<div style='display: flex; justify-content: space-between;'><span>Decrease (Red)</span><span>Increase (Blue)</span></div>", unsafe_allow_html=True)
        
#     else:
#         img = apply_mask(diffClass)
#         m.add_ee_layer(img.select('albedo_difference').selfMask(), {'min': 0, 'max': 1, 'palette': black_red}, 'albedo boundary', True)
#         m.add_ee_layer(img.select('ndvi_difference').selfMask(), {'min': 0, 'max': 1, 'palette': black_red}, 'ndvi boundary', False)
#         m.add_ee_layer(img.select('ndmi_difference').selfMask(), {'min': 0, 'max': 1, 'palette': black_red}, 'ndmi boundary', False)
#         m.add_ee_layer(img.select('savi_difference').selfMask(), {'min': 0, 'max': 1, 'palette': black_red}, 'savi boundary', False)
#         m.add_ee_layer(img.select('SAR_difference_VV_classified').selfMask(), {'min': 0, 'max': 1, 'palette': black_red}, 'Sentinel-1 VV boundary', False)

#         st.sidebar.markdown("### Change Boundary")
#         st.sidebar.markdown("⬛ No Change / Background<br>🟥 Change Detected", unsafe_allow_html=True)

#     folium.LayerControl().add_to(m)
#     m.add_ee_layer(roads_styled, {}, 'Roads', True, 0.6)
#     st_folium(m, use_container_width=True, height=800, returned_objects=[])

# ---------------------------------------------
# MODE 2: METRICS
# ---------------------------------------------
elif '2.' in mode:
    # m.add_ee_layer(roads_styled, {}, 'Roads', True, 0.6)
    m.add_ee_layer(apply_mask(after), {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 0.35}, 'After True Color', True)
    
    metric_type = st.sidebar.selectbox('Select metric classification type:', [
        'Unclassified Change Metrics (Raw Differences)', 
        'Classified Change Metrics (Boundaries)'
    ])
    
    # NEW: Dropdown to select a specific metric to prevent API timeouts
    metric_options = {
        'Albedo': 'albedo_difference',
        'NDVI (Vegetation)': 'ndvi_difference',
        'NDMI (Moisture)': 'ndmi_difference',
        'SAVI (Vegetation)': 'savi_difference',
        'Sentinel-1 VV (SAR)': 'SAR_difference_VV' 
    }
    
    choice = st.sidebar.selectbox('Select specific metric to view:', list(metric_options.keys()))
    band_name = metric_options[choice]
    
    if 'Unclassified' in metric_type:
        img = apply_mask(diffClassMasked)
        
        # SAR has a different min/max range than the optical indices
        if 'SAR' in choice:
            vis = {'min': -10, 'max': 10, 'palette': rdbu}
        else:
            vis = {'min': -0.2, 'max': 0.2, 'palette': rdbu}
            
        m.add_ee_layer(img.select(band_name), vis, f'{choice} Difference', True)
        
        st.sidebar.markdown("### Difference (RdBu Scale)")
        st.sidebar.markdown("<div style='background: linear-gradient(to right, red, white, blue); height: 15px; border-radius: 5px;'></div>", unsafe_allow_html=True)
        st.sidebar.markdown("<div style='display: flex; justify-content: space-between;'><span>Decrease (Red)</span><span>Increase (Blue)</span></div>", unsafe_allow_html=True)
        
    else:
        img = apply_mask(diffClass)
        
        # The SAR band has a slightly different name in the classified image
        if 'SAR' in choice:
            band_name = 'SAR_difference_VV_classified'
            
        m.add_ee_layer(img.select(band_name).selfMask(), {'min': 0, 'max': 1, 'palette': black_red}, f'{choice} Boundary', True)
        
        st.sidebar.markdown("### Change Boundary")
        st.sidebar.markdown("⬛ No Change / Background<br>🟥 Change Detected", unsafe_allow_html=True)
    m.add_ee_layer(roads_styled, {}, 'Roads', True, 0.6)

    folium.LayerControl().add_to(m)


# ---------------------------------------------
# MODE 3: BOUNDARIES
# ---------------------------------------------
elif '3.' in mode:
    # m.add_ee_layer(roads_styled, {}, 'Roads', True, 0.6)
    
    boundary_options = {
        'Sum of Change Detected Pixels (5 means total agreement)': {'band': 'summed_change', 'min': 0, 'max': 3, 'palette': agreement_palette},
        'Surface Change High Confidence': {'band': 'surface_change_high_confidence', 'min': 0, 'max': 4, 'palette': ['red']},
        'Surface Change Medium Confidence': {'band': 'surface_change_medium_confidence', 'min': 0, 'max': 3, 'palette': ['orange']},
        'Surface Change Low Confidence': {'band': 'surface_change_low_confidence', 'min': 0, 'max': 2, 'palette': ['yellow']}
    }
    
    choice = st.sidebar.selectbox('Select a boundary summary to visualize:', list(boundary_options.keys()))
    params = boundary_options[choice]
    
    m.add_ee_layer(apply_mask(summaryChange.select(params['band'])), 
               {'min': params['min'], 'max': params['max'], 'palette': params['palette']}, 
               choice)
    
    if choice == 'Sum of Change Detected Pixels (5 means total agreement)':
        st.sidebar.markdown("### Algorithm Agreement Score")
        st.sidebar.markdown("⬜ 0-1 (Low)<br>🟨 2<br>🟧 3<br>🟥 4+ (High)", unsafe_allow_html=True)
    else:
        color_map = {'red': '🟥', 'orange': '🟧', 'yellow': '🟨'}
        st.sidebar.markdown(f"### Legend")
        st.sidebar.markdown(f"{color_map[params['palette'][0]]} Change Detected", unsafe_allow_html=True)

    m.add_ee_layer(roads_styled, {}, 'Roads', True, 0.6)

    folium.LayerControl().add_to(m)
    # st_folium(m, use_container_width=True, height=800, returned_objects=[])

# =================================================================
# 4. Render the Map
# =================================================================
# Display the map using streamlit-folium instead of geemap
# st_folium(m, use_container_width=True, height=800)
st_folium(m, use_container_width=True, height=800, returned_objects=[])
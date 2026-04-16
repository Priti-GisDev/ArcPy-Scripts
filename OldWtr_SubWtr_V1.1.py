import arcpy
import os
import sys
import re

def sanitize_filename(name, max_length=100):
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name[:max_length]

def apply_highlight_symbology_red(layer, fill_color=[255, 0, 0, 100], stroke_color=[0, 0, 0, 0], stroke_width=0):
    try:
        cim_lyr = layer.getDefinition("V2")
        for sl in cim_lyr.renderer.symbol.symbol.symbolLayers:
            if sl.__class__.__name__ == "CIMSolidFill":
                sl.color.values = fill_color
            elif sl.__class__.__name__ == "CIMSolidStroke":
                sl.color.values = stroke_color
                sl.width = stroke_width
        layer.setDefinition(cim_lyr)
    except Exception as e:
        arcpy.AddWarning("❗ Symbol update issue in layer '{}' : {}".format(layer.name, str(e)))

def apply_highlight_symbology_blue(layer, fill_color=[0, 169, 230, 100], stroke_color=[0, 0, 0, 0], stroke_width=0):
    try:
        cim_lyr = layer.getDefinition("V2")
        for sl in cim_lyr.renderer.symbol.symbol.symbolLayers:
            if sl.__class__.__name__ == "CIMSolidFill":
                sl.color.values = fill_color
            elif sl.__class__.__name__ == "CIMSolidStroke":
                sl.color.values = stroke_color
                sl.width = stroke_width
        layer.setDefinition(cim_lyr)
    except Exception as e:
        arcpy.AddWarning("❗ Symbol update issue in layer '{}' : {}".format(layer.name, str(e)))

def apply_buffered_extent(map_frame, extent, buffer_ratio=0.1):
    if extent:
        try:
            buffer_x = (extent.XMax - extent.XMin) * buffer_ratio
            buffer_y = (extent.YMax - extent.YMin) * buffer_ratio
            extent.XMin -= buffer_x
            extent.XMax += buffer_x
            extent.YMin -= buffer_y
            extent.YMax += buffer_y
            map_frame.camera.setExtent(extent)
        except Exception as e:
            arcpy.AddWarning("⚠️ Failed to apply extent buffer: {}".format(str(e)))
    else:
        arcpy.AddWarning("⚠️ Extent is None. Skipping camera update.")

# ------------------- Inputs -------------------
pagx_template_folder = arcpy.GetParameterAsText(0)
layout_level = arcpy.GetParameterAsText(1).strip().lower()
output_folder = arcpy.GetParameterAsText(2).strip()

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

arcpy.AddMessage("\n🛠️ Process Started.")

# Fixed case-sensitivity issue
if layout_level not in ["subwatershed", "miniwatershed", "microwatershed"]:
    arcpy.AddError("❌ Invalid layout level.")
    sys.exit()

expected_filename = layout_level + ".pagx"
pagx_template = None
for file in os.listdir(pagx_template_folder):
    if file.lower() == expected_filename:
        pagx_template = os.path.join(pagx_template_folder, file)
        break

if not pagx_template or not os.path.exists(pagx_template):
    arcpy.AddError(f"❌ Template '{expected_filename}' not found in {pagx_template_folder}")
    sys.exit()

arcpy.AddMessage(f"📄 Using template: {pagx_template}")
aprx = arcpy.mp.ArcGISProject("CURRENT")

# ------------------- Constants -------------------
watershed_field = "watershed"
subwatershed_field = "subwshed"
exported_count = 0

# ------------------- Use first layout to list unique Bana -------------------
layout_template = aprx.importDocument(pagx_template)

# --- Function to get a frame by exact name ---
def get_frame_by_name(layout, target_name):
    return next(
        (mf for mf in layout.listElements("MAPFRAME_ELEMENT")
         if mf.name.strip().lower() == target_name.strip().lower()),
        None
    )
# --- Get the exact frames ---
subwatershed_frame = get_frame_by_name(layout_template, "SubWatershed Frame")

# --- Exit if either frame is missing ---
if not subwatershed_frame:
    arcpy.AddWarning("⚠️ Frame not found.")
    sys.exit()

subwatershed_map = subwatershed_frame.map

subwatershed_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "SUBWATERSHED" and lyr.isFeatureLayer), None)

if not subwatershed_layer :
    arcpy.AddWarning("⚠️ Layer not found.")
    sys.exit()

unique_watershed = sorted({row[0].strip() for row in arcpy.da.SearchCursor(subwatershed_layer, [watershed_field]) if row[0]})

# ------------------- Loop Watershed -------------------
for watershed_name in unique_watershed:
    arcpy.AddMessage(f"\n🔎 Watershed: {watershed_name}")
    watershed_clean = watershed_name.strip().upper().replace("'", "''")
    where_clause = f"UPPER({watershed_field}) = '{watershed_clean}'"

    layout_template = aprx.importDocument(pagx_template)
    subwatershed_frame = get_frame_by_name(layout_template, "SubWatershed Frame")

    if not subwatershed_frame :
        arcpy.AddWarning("⚠️ Map frame not found.")
        continue

    subwatershed_map = subwatershed_frame.map

    subwatershed_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "SUBWATERSHED" and lyr.isFeatureLayer), None)

    if not subwatershed_layer :
        arcpy.AddWarning("⚠️ Layer not found.")
        continue

    state_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "STATE" and lyr.isFeatureLayer), None)
    if not state_layer:
        arcpy.AddWarning("⚠️ Layer state not found.")
        continue

    subwatershed_layer.definitionQuery = where_clause
    count = int(arcpy.management.GetCount(subwatershed_layer)[0])
    arcpy.AddMessage(f"📋 Found {count} subwatershed.")

    if count == 0:
        continue

    highlight_subwatershed = sorted({row[0] for row in arcpy.da.SearchCursor(subwatershed_layer, [subwatershed_field], where_clause) if row[0]})

    for subwatershed_index, subwatershed_name in enumerate(highlight_subwatershed, 1):
        arcpy.AddMessage(f"📌 {subwatershed_index}. Processing: {subwatershed_name}")

        layout_template = aprx.importDocument(pagx_template)
        subwatershed_frame = get_frame_by_name(layout_template, "SubWatershed Frame")

        if not subwatershed_frame :
            arcpy.AddWarning("⚠️ Map frame not found.")
            continue

        subwatershed_map = subwatershed_frame.map

        subwatershed_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "SUBWATERSHED" and lyr.isFeatureLayer), None)

        if not subwatershed_layer:
            arcpy.AddWarning("⚠️ Layer not found.")
            continue

        state_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "STATE" and lyr.isFeatureLayer), None)
        if not state_layer:
            arcpy.AddWarning("⚠️ Layer state not found.")
            continue
        
        subwatershed_layer.definitionQuery = where_clause
        subwatershed_clean = subwatershed_name.replace("'", "''")
        subwatershed_query = f"{subwatershed_field} = '{subwatershed_clean}'"

        arcpy.management.SelectLayerByAttribute(subwatershed_layer, "NEW_SELECTION", subwatershed_query)
        extent = subwatershed_frame.getLayerExtent(state_layer, False, True)
        arcpy.management.SelectLayerByAttribute(subwatershed_layer, "CLEAR_SELECTION")
        apply_buffered_extent(subwatershed_frame, extent)

        subwatershed_fc = os.path.join(arcpy.env.scratchGDB, "highlight_subwatershed")
        if arcpy.Exists(subwatershed_fc):
            arcpy.management.Delete(subwatershed_fc)
        arcpy.conversion.FeatureClassToFeatureClass(subwatershed_layer, arcpy.env.scratchGDB, "highlight_subwatershed", subwatershed_query)

        subwatershed_highlight_layer = subwatershed_map.addDataFromPath(subwatershed_fc)
        subwatershed_highlight_layer.name = "Highlightsubwatershed"
        subwatershed_map.moveLayer(subwatershed_layer, subwatershed_highlight_layer, "BEFORE")
        apply_highlight_symbology_red(subwatershed_highlight_layer)

        safe_subwatershed = sanitize_filename(subwatershed_name)
        subwatershed_png = os.path.join(output_folder, f"{safe_subwatershed}.png")
        subwatershed_frame.exportToPNG(subwatershed_png, resolution=300)

        subwatershedpic = next((el for el in layout_template.listElements("PICTURE_ELEMENT") if el.name == "SubWatershed Map"), None)
        if subwatershedpic:
            subwatershedpic.sourceImage = subwatershed_png

        subwatershed_text = next((el for el in layout_template.listElements("TEXT_ELEMENT") if el.name == "SubWatershed Name"), None)
        if subwatershed_text:
            subwatershed_text.text = subwatershed_name
            name_length = len(subwatershed_name)
            
            if name_length > 15:
                subwatershed_text.textSize = 10  # shrink font
            else:
                subwatershed_text.textSize = 12 

        pagx_path = os.path.join(output_folder, f"{safe_subwatershed}.pagx")
        layout_template.exportToPAGX(pagx_path)
        arcpy.AddMessage(f"✅ Exported: {pagx_path}")
        exported_count += 1
        
        if subwatershed_highlight_layer:
            subwatershed_map.removeLayer(subwatershed_highlight_layer)
        if arcpy.Exists(subwatershed_fc):
            arcpy.management.Delete(subwatershed_fc)

    subwatershed_layer.definitionQuery = ""

arcpy.AddMessage(f"\n🏁 All subwatershed layouts exported successfully. Total: {exported_count}")

# ------------------- Delete All PNG Files -------------------
deleted_count = 0
for file_name in os.listdir(output_folder):
    if file_name.lower().endswith(".png"):
        try:
            file_path = os.path.join(output_folder, file_name)
            os.remove(file_path)
            deleted_count += 1
        except Exception as e:
            arcpy.AddWarning("⚠️ Failed to delete '{}': {}".format(file_name, str(e)))
arcpy.AddMessage(f"\n🧹 Deleted {deleted_count} JPG files from output folder.")

arcpy.AddMessage("\n🌟 Process Completed.")

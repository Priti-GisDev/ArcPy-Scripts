import arcpy
import os
import sys
import time
import re

# ------------------- Cut Down Long Name -------------------
def sanitize_filename(name, max_length=100):
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name[:max_length]  

# ------------------- Apply Highlight Red Colour -------------------
def apply_highlight_symbology(layer, fill_color=[255, 0, 0, 100], stroke_color=[0, 0, 0, 0], stroke_width=0):
    """
    Applies red fill and transparent stroke symbology to the input layer using CIM.

    Parameters:
        layer (arcpy.mp.Layer): The layer to apply symbology.
        fill_color (list): RGBA values for fill color.
        stroke_color (list): RGBA values for stroke color.
        stroke_width (float): Width of the stroke (default is 0).
    """
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
        arcpy.AddWarning("❗ Symbol update issue in layer '{}': {}".format(layer.name, str(e)))

# ------------------- Map Extend with Buffer -------------------
def apply_buffered_extent(map_frame, extent, buffer_ratio=0.1):
    """
    Applies a buffered extent to the given map frame's camera.

    Parameters:
        map_frame (arcpy.mp.MapFrame): The map frame to set the extent on.
        extent (arcpy.Extent): The extent to buffer.
        buffer_ratio (float): Buffer percentage (default is 10%).
    """
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

# ------------------- Input Parameters -------------------
pagx_template_folder = arcpy.GetParameterAsText(0)
layout_level = arcpy.GetParameterAsText(1)
output_folder = arcpy.GetParameterAsText(2).strip()

if not os.path.exists(output_folder):
    try:
        os.makedirs(output_folder)
    except Exception as e:
        arcpy.AddError(f"❌ Failed to create output folder: {output_folder}\n{str(e)}")
        sys.exit()
arcpy.AddMessage("\n Process Started.")

# ------------------- Normalize layout level -------------------
layout_level = layout_level.lower().strip()
valid_levels = ["district", "taluka", "village"]

if layout_level not in valid_levels:
    arcpy.AddError("\u274c Invalid layout level. Use: district, taluka, or village.")
    sys.exit()

# ------------------- Find PAGX Template -------------------
expected_filename = layout_level + ".pagx"
pagx_template = None

for file in os.listdir(pagx_template_folder):
    if file.lower() == expected_filename:
        pagx_template = os.path.join(pagx_template_folder, file)
        break

if not pagx_template or not os.path.exists(pagx_template):
    found_templates = [f for f in os.listdir(pagx_template_folder) if f.lower().endswith(".pagx")]
    arcpy.AddError(f"\u274c Could not find '{expected_filename}' in: {pagx_template_folder}")
    arcpy.AddError(f"\ud83d\udcc2 Available templates: {', '.join(found_templates)}")
    sys.exit()

arcpy.AddMessage(f"\ud83d\udcc4 Using template: {pagx_template}")
aprx = arcpy.mp.ArcGISProject("CURRENT")

# ------------------- Taluka Layout Logic -------------------
if layout_level == "taluka":
    district_field = "DistrictName"
    taluka_field = "TalukaName"
    exported_count = 0  

    layout_template = aprx.importDocument(pagx_template)
    district_frame = next((mf for mf in layout_template.listElements("MAPFRAME_ELEMENT") if "district frame" in mf.name.lower()), None)
    if not district_frame:
        arcpy.AddError("❌ District frame not found in layout.")
        sys.exit()

    district_map = district_frame.map
    reference_layer = next((lyr for lyr in district_map.listLayers() if lyr.name.upper() == "DISTRICT"), None)
    if not reference_layer:
        arcpy.AddError("❌ DISTRICT layer not found in district map.")
        sys.exit()

    district_names = sorted({row[0].strip() for row in arcpy.da.SearchCursor(reference_layer, [district_field]) if row[0]})
    arcpy.AddMessage(f"📋 Found {len(district_names)} districts to process.")
   
    for district_index, district_name in enumerate(district_names, 1):
        arcpy.AddMessage(f"\n📌 Processing District: {district_index}. {district_name}")

        layout_template = aprx.importDocument(pagx_template)
        district_frame = next((mf for mf in layout_template.listElements("MAPFRAME_ELEMENT") if "district frame" in mf.name.lower()), None)
        taluka_frame = next((mf for mf in layout_template.listElements("MAPFRAME_ELEMENT") if "taluka frame" in mf.name.lower()), None)

        if not district_frame or not taluka_frame:
            arcpy.AddError("❌ Required map frames missing in layout.")
            continue

        district_map = district_frame.map
        taluka_map = taluka_frame.map

        district_layer = next((lyr for lyr in district_map.listLayers() if lyr.name.upper() == "DISTRICT"), None)
        taluka_layer = next((lyr for lyr in taluka_map.listLayers() if lyr.name.upper() == "TEHSIL"), None)

        if not district_layer or not taluka_layer:
            arcpy.AddError("❌ Required layers not found.")
            continue
    
        # ------------------- Process Each District -------------------
        district_query = "{0} = '{1}'".format(district_field, district_name.replace("'", "''"))
        arcpy.management.SelectLayerByAttribute(district_layer, "NEW_SELECTION", district_query)
        district_extent = district_frame.getLayerExtent(district_layer, False, True)
        arcpy.management.SelectLayerByAttribute(district_layer, "CLEAR_SELECTION")
        apply_buffered_extent(district_frame, district_extent)

        district_fc = os.path.join(arcpy.env.scratchGDB, "highlight_district")
        if arcpy.Exists(district_fc):
            arcpy.management.Delete(district_fc)
        arcpy.conversion.FeatureClassToFeatureClass(district_layer, arcpy.env.scratchGDB, "highlight_district", district_query)

        district_highlight_layer = district_map.addDataFromPath(district_fc)
        district_highlight_layer.name = "HighlightDistrict"
        district_map.moveLayer(district_layer, district_highlight_layer, "BEFORE")
        apply_highlight_symbology(district_highlight_layer)

        safe_district = sanitize_filename(district_name)
        district_jpg = os.path.join(output_folder, f"{safe_district}.jpg")
        district_frame.exportToJPEG(district_jpg, resolution=150, jpeg_quality=70)
        stored_district_jpg = district_jpg
        
        district_pic = next((el for el in layout_template.listElements("PICTURE_ELEMENT") if el.name == "DistrictMap"), None)
        if district_pic:
            district_pic.sourceImage = stored_district_jpg

        district_text = next((el for el in layout_template.listElements("TEXT_ELEMENT") if el.name == "DistrictName"), None)
        if district_text:
            district_text.text = district_name
            name_length = len(district_name)
            
            if name_length > 15:
                district_text.textSize = 10  # shrink font
            else:
                district_text.textSize = 12 
                
        # ------------------- Process Each Taluka -------------------
        taluka_layer.definitionQuery = district_query
        arcpy.management.SelectLayerByAttribute(taluka_layer, "NEW_SELECTION", district_query)
        taluka_extent = taluka_frame.getLayerExtent(taluka_layer, False, True)
        arcpy.management.SelectLayerByAttribute(taluka_layer, "CLEAR_SELECTION")
        apply_buffered_extent(taluka_frame, taluka_extent)

        taluka_names = sorted({row[0].strip() for row in arcpy.da.SearchCursor(taluka_layer, [taluka_field], district_query) if row[0]})
        if not taluka_names:
            arcpy.AddWarning(f"⚠️ No talukas found for: {district_name}")
            continue

        for taluka_index, taluka_name in enumerate(taluka_names, 1):
            arcpy.AddMessage(f"  ✅ Taluka: {taluka_index}. {taluka_name}")

            taluka_query = "{0} = '{1}' AND {2} = '{3}'".format(
                district_field, district_name.replace("'", "''"),
                taluka_field, taluka_name.replace("'", "''")
            )

            taluka_fc = os.path.join(arcpy.env.scratchGDB, "highlight_taluka")
            if arcpy.Exists(taluka_fc):
                arcpy.management.Delete(taluka_fc)
            arcpy.conversion.FeatureClassToFeatureClass(taluka_layer, arcpy.env.scratchGDB, "highlight_taluka", taluka_query)

            taluka_highlight_layer = taluka_map.addDataFromPath(taluka_fc)
            taluka_highlight_layer.name = "HighlightTaluka"
            taluka_map.moveLayer(taluka_layer, taluka_highlight_layer, "BEFORE")
            apply_highlight_symbology(taluka_highlight_layer)

            safe_district = sanitize_filename(district_name)
            safe_taluka = sanitize_filename(taluka_name)
            taluka_jpg = os.path.join(output_folder, f"{safe_taluka}_{safe_district}.jpg")
            taluka_frame.exportToJPEG(taluka_jpg, resolution=150, jpeg_quality=70)
            taluka_pic = next((el for el in layout_template.listElements("PICTURE_ELEMENT") if el.name == "TalukaMap"), None)
            if taluka_pic:
                taluka_pic.sourceImage = taluka_jpg
            
            taluka_text = next((el for el in layout_template.listElements("TEXT_ELEMENT") if el.name == "TalukaName"), None)                
            if taluka_text:
                taluka_text.text = taluka_name
                name_length = len(taluka_name)            
                if name_length > 15:
                    taluka_text.textSize = 10  # shrink font
                else:
                    taluka_text.textSize = 12
                
            out_name = f"{safe_taluka}_{safe_district}.pagx"
            out_path = os.path.join(output_folder, out_name)

            if os.path.exists(out_path):
                arcpy.AddMessage(f"      ⏩ Skipped (already exists): {out_name}")
                continue
                    
            layout_template.exportToPAGX(out_path)
            exported_count += 1 
            arcpy.AddMessage(f"      ✅ Exported: {out_name}")

            if taluka_highlight_layer:
                taluka_map.removeLayer(taluka_highlight_layer)
            if arcpy.Exists(taluka_fc):
                arcpy.management.Delete(taluka_fc)

        taluka_layer.definitionQuery = ""  # 🧹 Reset after each district

        try:
            if district_highlight_layer and district_highlight_layer in district_map.listLayers():
                district_map.removeLayer(district_highlight_layer)
        except Exception as e:
            arcpy.AddWarning("⚠️ Could not remove district highlight layer: " + str(e))

        if arcpy.Exists(district_fc):
            arcpy.management.Delete(district_fc)
    
    arcpy.AddMessage(f"🏁 Completed {len(taluka_names)} talukas for {district_name}.")
arcpy.AddMessage("\n🌟 All taluka layouts exported successfully. Total exported: {0}".format(exported_count))
   
# ------------------- Delete All PNG Files -------------------
deleted_count = 0
for file_name in os.listdir(output_folder):
    if file_name.lower().endswith(".jpg"):
        try:
            file_path = os.path.join(output_folder, file_name)
            os.remove(file_path)
            deleted_count += 1
        except Exception as e:
            arcpy.AddWarning("⚠️ Failed to delete '{}': {}".format(file_name, str(e)))
arcpy.AddMessage(f"\n🧹 Deleted {deleted_count} JPG files from output folder.")

arcpy.AddMessage("\n🌟 Process Completed.")
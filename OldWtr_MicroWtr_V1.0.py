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

def get_frame_by_name(layout, target_name):
    return next(
        (mf for mf in layout.listElements("MAPFRAME_ELEMENT") if mf.name.strip().lower() == target_name.strip().lower()), None)

# ------------------- Inputs -------------------
pagx_template_folder = arcpy.GetParameterAsText(0)
layout_level = arcpy.GetParameterAsText(1).strip().lower()
output_folder = arcpy.GetParameterAsText(2).strip()
target_subcatchment = arcpy.GetParameterAsText(3).strip()

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

arcpy.AddMessage("\n🛠️ Process Started.")

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
subwatershed_field = "subwshed1"
miniwatershed_field = "miniwshed1"
microwatershed_field = "microwshed1"
subcatchment_field = "subcatchme"
exported_count = 0

layout_template = aprx.importDocument(pagx_template)

subwatershed_frame = get_frame_by_name(layout_template, "SubWatershed Frame")
miniwatershed_frame = get_frame_by_name(layout_template, "MiniWatershed Frame")

if not subwatershed_frame or not miniwatershed_frame :
    arcpy.AddWarning("⚠️ Frame not found.")
    sys.exit()

subwatershed_map = subwatershed_frame.map
miniwatershed_map = miniwatershed_frame.map

subwatershed_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "WATERSHED_SUBWATERSHED" and lyr.isFeatureLayer), None)
miniwatershed_layer = next((lyr for lyr in miniwatershed_map.listLayers() if lyr.name.upper() == "WATERSHED_MINIWSHED" and lyr.isFeatureLayer), None)

if not subwatershed_layer or not miniwatershed_layer :
    arcpy.AddWarning("⚠️ Layer not found.")
    sys.exit()

# ------------------- Select target subcatchment -------------------
subcatch_field_delim = arcpy.AddFieldDelimiters(subwatershed_layer, subcatchment_field)
subcatch_value = target_subcatchment.replace("'", "''")
subcatch_query = "{} = '{}'".format(subcatch_field_delim, subcatch_value)

unique_watershed = sorted({ row[0].strip() for row in arcpy.da.SearchCursor(subwatershed_layer, [watershed_field, subcatchment_field]) if row[1] and row[1].strip() == target_subcatchment})

if not unique_watershed:
    arcpy.AddError(f"❌ No watershed found for subcatchment '{target_subcatchment}'.")
    sys.exit()

arcpy.AddMessage(f"✅ Found {len(unique_watershed)} watershed(s) for subcatchment '{target_subcatchment}': {unique_watershed}")

# ------------------- Loop Watershed -------------------
for watershed_name in unique_watershed:
    arcpy.AddMessage(f"\n🔎 Watershed: {watershed_name}")

    subcatch_field_delim = arcpy.AddFieldDelimiters(subwatershed_layer, subcatchment_field)
    watershed_field_delim = arcpy.AddFieldDelimiters(subwatershed_layer, watershed_field)

    subcatch_value = target_subcatchment.replace("'", "''")
    watershed_clean = watershed_name.strip().replace("'", "''")

    watershed_query = "{0} = '{1}' AND {2} = '{3}'".format(
        subcatch_field_delim, subcatch_value,
        watershed_field_delim, watershed_clean
    )    
    layout_template = aprx.importDocument(pagx_template)
    subwatershed_frame = get_frame_by_name(layout_template, "SubWatershed Frame")
    miniwatershed_frame = get_frame_by_name(layout_template, "MiniWatershed Frame")

    if not subwatershed_frame or not miniwatershed_frame:
        arcpy.AddWarning("⚠️ Map frame not found.")
        continue

    subwatershed_map = subwatershed_frame.map
    miniwatershed_map = miniwatershed_frame.map

    subwatershed_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "WATERSHED_SUBWATERSHED" and lyr.isFeatureLayer), None)
    miniwatershed_layer = next((lyr for lyr in miniwatershed_map.listLayers() if lyr.name.upper() == "WATERSHED_MINIWSHED" and lyr.isFeatureLayer), None)

    if not subwatershed_layer or not miniwatershed_layer:
        arcpy.AddWarning("⚠️ Layer not found.")
        continue

    state_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "STATE" and lyr.isFeatureLayer), None)
    if not state_layer:
        arcpy.AddWarning("⚠️ Layer state not found.")
        continue

    subwatershed_layer.definitionQuery = watershed_query
    count = int(arcpy.management.GetCount(subwatershed_layer)[0])
    if count == 0:
        continue

    subwatershed_names = [row[0].strip() for row in arcpy.da.SearchCursor( subwatershed_layer, [subwatershed_field], watershed_query) if row[0]]

    arcpy.AddMessage(f"✅ Found {len(subwatershed_names)} subwatershed(s) in '{watershed_name}': {subwatershed_names}")

    # ------------------- Loop over Subwatersheds -------------------    
    for subwatershed_index, subwatershed_name in enumerate(subwatershed_names, 1):
        arcpy.AddMessage(f"📌 {subwatershed_index}. Processing: {subwatershed_name}")

        layout_template = aprx.importDocument(pagx_template)
        subwatershed_frame = get_frame_by_name(layout_template, "SubWatershed Frame")
        miniwatershed_frame = get_frame_by_name(layout_template, "MiniWatershed Frame")

        if not subwatershed_frame or not miniwatershed_frame:
            arcpy.AddWarning("⚠️ Map frame not found.")
            continue

        subwatershed_map = subwatershed_frame.map
        miniwatershed_map = miniwatershed_frame.map

        subwatershed_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "WATERSHED_SUBWATERSHED" and lyr.isFeatureLayer), None)
        miniwatershed_layer = next((lyr for lyr in miniwatershed_map.listLayers() if lyr.name.upper() == "WATERSHED_MINIWSHED" and lyr.isFeatureLayer), None)

        if not subwatershed_layer or not miniwatershed_layer:
            arcpy.AddWarning("⚠️ Layer not found.")
            continue

        state_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "STATE" and lyr.isFeatureLayer), None)
        if not state_layer:
            arcpy.AddWarning("⚠️ Layer state not found.")
            continue
        
        subwatershed_layer.definitionQuery = watershed_query
        subwatershed_clean = subwatershed_name.replace("'", "''")

        subwatershed_query = "{0} = '{1}' AND {2} = '{3}' AND {4} = '{5}'".format(
            subcatch_field_delim, subcatch_value,
            watershed_field_delim, watershed_clean,
            arcpy.AddFieldDelimiters(subwatershed_layer, subwatershed_field), subwatershed_clean
        )

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

        # ------------------- Export Miniwatershed Layouts -------------------
        miniwatershed_layer.definitionQuery = subwatershed_query
        arcpy.management.SelectLayerByAttribute(miniwatershed_layer, "NEW_SELECTION", subwatershed_query)
        miniwatershed_extent = miniwatershed_frame.getLayerExtent(miniwatershed_layer, False, True)
        arcpy.management.SelectLayerByAttribute(miniwatershed_layer, "CLEAR_SELECTION")
        apply_buffered_extent(miniwatershed_frame, miniwatershed_extent)

        miniwatershed_names = sorted({row[0].strip() for row in arcpy.da.SearchCursor(miniwatershed_layer, [miniwatershed_field], subwatershed_query) if row[0]})
       
        if not miniwatershed_names:
            arcpy.AddWarning(f"⚠️ No miniwatershed found for: {subwatershed_name}")
            continue
        
        arcpy.AddMessage(f"✅ Found {len(miniwatershed_names)} miniwatershed(s) in '{subwatershed_name}': {miniwatershed_names}")

        for miniwatershed_index, miniwatershed_name in enumerate(miniwatershed_names, 1):
            arcpy.AddMessage(f"  ✅ miniwatershed: {miniwatershed_index}. {miniwatershed_name}")
            
            layout_template = aprx.importDocument(pagx_template)
            subwatershed_frame = get_frame_by_name(layout_template, "SubWatershed Frame")
            miniwatershed_frame = get_frame_by_name(layout_template, "MiniWatershed Frame")
            microwatershed_frame = get_frame_by_name(layout_template, "MicroWatershed Frame")

            if not subwatershed_frame or not miniwatershed_frame or not microwatershed_frame:
                arcpy.AddWarning("⚠️ Map frame not found.")
                continue

            subwatershed_map = subwatershed_frame.map
            miniwatershed_map = miniwatershed_frame.map
            microwatershed_map = microwatershed_frame.map

            subwatershed_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "WATERSHED_SUBWATERSHED" and lyr.isFeatureLayer), None)
            miniwatershed_layer = next((lyr for lyr in miniwatershed_map.listLayers() if lyr.name.upper() == "WATERSHED_MINIWSHED" and lyr.isFeatureLayer), None)
            microwatershed_layer = next((lyr for lyr in microwatershed_map.listLayers() if lyr.name.upper() == "WATERSHED_MICROWSHED" and lyr.isFeatureLayer), None)

            if not subwatershed_layer or not miniwatershed_layer or not microwatershed_layer:
                arcpy.AddWarning("⚠️ Layer not found.")
                continue

            state_layer = next((lyr for lyr in subwatershed_map.listLayers() if lyr.name.upper() == "STATE" and lyr.isFeatureLayer), None)
            if not state_layer:
                arcpy.AddWarning("⚠️ Layer state not found.")
                continue

            miniwatershed_query = "{0} = '{1}' AND {2} = '{3}' AND {4} = '{5}'".format(
                subcatch_field_delim, subcatch_value,
                arcpy.AddFieldDelimiters(miniwatershed_layer, watershed_field), watershed_clean,
                arcpy.AddFieldDelimiters(miniwatershed_layer, subwatershed_field), subwatershed_name.replace("'", "''")
            )
            
            if miniwatershed_name:
                miniwatershed_query += " AND {0} = '{1}'".format(
                    arcpy.AddFieldDelimiters(miniwatershed_layer, miniwatershed_field), miniwatershed_name.replace("'", "''")
                )

            miniwatershed_layer.definitionQuery = subwatershed_query
            arcpy.management.SelectLayerByAttribute(miniwatershed_layer, "NEW_SELECTION", subwatershed_query)
            miniwatershed_extent = miniwatershed_frame.getLayerExtent(miniwatershed_layer, False, True)
            arcpy.management.SelectLayerByAttribute(miniwatershed_layer, "CLEAR_SELECTION")
            apply_buffered_extent(miniwatershed_frame, miniwatershed_extent)

            miniwatershed_fc = os.path.join(arcpy.env.scratchGDB, "highlight_miniwatershed")
            if arcpy.Exists(miniwatershed_fc):
                arcpy.management.Delete(miniwatershed_fc)
            arcpy.conversion.FeatureClassToFeatureClass(miniwatershed_layer, arcpy.env.scratchGDB, "highlight_miniwatershed", miniwatershed_query)

            miniwatershed_highlight_layer = miniwatershed_map.addDataFromPath(miniwatershed_fc)
            miniwatershed_highlight_layer.name = "Highlightminiwatershed"
            miniwatershed_map.moveLayer(miniwatershed_layer, miniwatershed_highlight_layer, "BEFORE")
            apply_highlight_symbology_blue(miniwatershed_highlight_layer)

            safe_subwatershed = sanitize_filename(subwatershed_name)
            safe_miniwatershed = sanitize_filename(miniwatershed_name)
            miniwatershed_jpg = os.path.join(output_folder, f"{safe_miniwatershed}_{safe_subwatershed}.jpg")
            miniwatershed_frame.exportToJPEG(miniwatershed_jpg, resolution=150, jpeg_quality=70)

            # ------------------- Export Microwatershed Layouts -------------------
            microwatershed_layer.definitionQuery = miniwatershed_query
            arcpy.management.SelectLayerByAttribute(microwatershed_layer, "NEW_SELECTION", miniwatershed_query)
            microwatershed_extent = microwatershed_frame.getLayerExtent(microwatershed_layer, False, True)
            arcpy.management.SelectLayerByAttribute(microwatershed_layer, "CLEAR_SELECTION")
            apply_buffered_extent(microwatershed_frame, microwatershed_extent)

            microwatershed_names = sorted({row[0].strip() for row in arcpy.da.SearchCursor(microwatershed_layer, [microwatershed_field], miniwatershed_query) if row[0]})
            arcpy.AddMessage(f"    📍 microwatersheds found in {miniwatershed_name}: {len(microwatershed_names)}")

            if not microwatershed_names:
                arcpy.AddWarning(f"⚠️ No microwatershed found for: {miniwatershed_name}")
                continue

            for microwatershed_index, microwatershed_name in enumerate(microwatershed_names, 1):
            
                # Skip if already exported
                safe_subwatershed = sanitize_filename(subwatershed_name)
                safe_miniwatershed = sanitize_filename(miniwatershed_name)
                safe_microwatershed = sanitize_filename(microwatershed_name)
                out_name = f"{safe_microwatershed}_{safe_miniwatershed}_{safe_subwatershed}.pagx"
                out_path = os.path.join(output_folder, out_name)

                if os.path.exists(out_path):
                    arcpy.AddMessage(f"      ⏩ Skipped (already exists): {out_name}")
                    continue

                arcpy.AddMessage(f"      📌 Processing microwatershed: {microwatershed_index}. {microwatershed_name}")

                microwatershed_query = "{0} = '{1}' AND {2} = '{3}' AND {4} = '{5}' AND {6} = '{7}'".format(
                    subcatch_field_delim, subcatch_value,
                    arcpy.AddFieldDelimiters(microwatershed_layer, watershed_field), watershed_clean,
                    arcpy.AddFieldDelimiters(microwatershed_layer, subwatershed_field), subwatershed_name.replace("'", "''"),
                    arcpy.AddFieldDelimiters(microwatershed_layer, miniwatershed_field), miniwatershed_name.replace("'", "''")
                )

                if microwatershed_name:
                    microwatershed_query += " AND {0} = '{1}'".format(
                        arcpy.AddFieldDelimiters(microwatershed_layer, microwatershed_field), microwatershed_name.replace("'", "''")
                    )

                microwatershed_fc = os.path.join(arcpy.env.scratchGDB, "highlight_microwatershed")
                if arcpy.Exists(microwatershed_fc):
                    arcpy.management.Delete(microwatershed_fc)
                arcpy.conversion.FeatureClassToFeatureClass(microwatershed_layer, arcpy.env.scratchGDB, "highlight_microwatershed", microwatershed_query)

                microwatershed_highlight_layer = microwatershed_map.addDataFromPath(microwatershed_fc)
                microwatershed_highlight_layer.name = "Highlightmicrowatershed"
                microwatershed_map.moveLayer(microwatershed_layer, microwatershed_highlight_layer, "BEFORE")
                apply_highlight_symbology_blue(microwatershed_highlight_layer)
                
                safe_microwatershed = sanitize_filename(microwatershed_name)
                microwatershed_jpg = os.path.join(output_folder, f"{safe_microwatershed}.jpg")
                microwatershed_frame.exportToJPEG(microwatershed_jpg, resolution=150, jpeg_quality=70)

                microwatershed_pic = next((el for el in layout_template.listElements("PICTURE_ELEMENT") if el.name == "MicroWatershed Map"), None)
                if microwatershed_pic:
                    microwatershed_pic.sourceImage = microwatershed_jpg
                
                microwatershed_text = next((el for el in layout_template.listElements("TEXT_ELEMENT") if el.name == "MicroWatershed Name"), None)                
                if microwatershed_text:
                    microwatershed_text.text = microwatershed_name
                    name_length = len(microwatershed_name)            
                    if name_length > 15:
                        microwatershed_text.textSize = 10  # shrink font
                    else:
                        microwatershed_text.textSize = 12

                miniwatershedpic = next((el for el in layout_template.listElements("PICTURE_ELEMENT") if el.name == "MiniWatershed Map"), None)
                if miniwatershedpic:
                    miniwatershedpic.sourceImage = miniwatershed_jpg

                miniwatershed_text = next((el for el in layout_template.listElements("TEXT_ELEMENT") if el.name == "MiniWatershed Name"), None)                
                if miniwatershed_text:
                    miniwatershed_text.text = miniwatershed_name
                    name_length = len(miniwatershed_name)            
                    if name_length > 15:
                        miniwatershed_text.textSize = 10  # shrink font
                    else:
                        miniwatershed_text.textSize = 12

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

                out_name = f"{safe_microwatershed}_{safe_miniwatershed}_{safe_subwatershed}.pagx"
                out_path = os.path.join(output_folder, out_name)
                layout_template.exportToPAGX(out_path)
                arcpy.AddMessage(f"    🏷️ Exported:{out_name}")
                exported_count += 1 

                if microwatershed_highlight_layer:
                    microwatershed_map.removeLayer(microwatershed_highlight_layer)
                if arcpy.Exists(microwatershed_fc):
                    arcpy.management.Delete(microwatershed_fc)

            microwatershed_layer.definitionQuery = "" 
            if miniwatershed_highlight_layer:
                miniwatershed_map.removeLayer(miniwatershed_highlight_layer)
            if arcpy.Exists(miniwatershed_fc):
                arcpy.management.Delete(miniwatershed_fc)
            arcpy.AddMessage(f"    🏷️ Exported:{out_name}")

        miniwatershed_layer.definitionQuery = ""
        try:
            if subwatershed_highlight_layer and subwatershed_highlight_layer in subwatershed_map.listLayers():
                subwatershed_map.removeLayer(subwatershed_highlight_layer)
        except Exception as e:
            arcpy.AddWarning("⚠️ Could not remove district highlight layer: " + str(e))

        if arcpy.Exists(subwatershed_fc):
            arcpy.management.Delete(subwatershed_fc)
    subwatershed_layer.definitionQuery = ""
arcpy.AddMessage("\n🌟 All microwatershed layouts exported successfully. Total exported: {0}".format(exported_count))

# ------------------- Delete All JPG Files -------------------
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
arcpy.AddMessage(f"\n🧹 Deleted {deleted_count} PNG files from output folder.")

arcpy.AddMessage("\n🌟 Process Completed.")



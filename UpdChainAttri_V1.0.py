"""
Title: Transfers chainage data
Project: IDDP (Orange Gate) 
Description: 
    This tool automates Transfers chainage data from the Point Feature Class to the respective Polygon Feature Class fields
"""
import arcpy
import os
import datetime

# --- Logger function for ArcGIS Pro messages ---
def log_msg(text):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    arcpy.AddMessage(f"{now} | {text}")

# --- Inputs from ArcGIS Pro Tool Parameters ---
poly_fc = arcpy.GetParameterAsText(0)  # Input Polygon Feature Class
point_fc = arcpy.GetParameterAsText(1) # Input Point Feature Class (with chainage data)

# Source field names in Point FC
in_ch_str = "chainage"         
in_ch_int = "chainagetotal"    

# Target field names in Polygon FC
f_from_str, f_to_str = "chainagefrom", "chainageto"
f_from_int, f_to_int = "chainagefromint", "chainagetoint"

try:
    # 1. Check Coordinate Systems
    poly_desc = arcpy.Describe(poly_fc)
    poly_sr = poly_desc.spatialReference
    log_msg(f"Polygon Coordinate System: {poly_sr.name}")

    # 2. Load all points into memory for speed
    points_list = []
    log_msg("Loading and projecting points...")
    
    with arcpy.da.SearchCursor(point_fc, ["SHAPE@", in_ch_str, in_ch_int, "OID@"]) as sc:
        for row in sc:
            # Project the point into the polygon's spatial reference to ensure distance accuracy
            geom = row[0].projectAs(poly_sr)
            points_list.append({
                "geom": geom, 
                "ch_str": row[1], 
                "ch_num": row[2], 
                "id": row[3]
            })
    
    log_msg(f"Total {len(points_list)} points loaded into memory.")

    # 3. Handle Workspace and Start Edit Session (Required for SDE/Versioned data)
    workspace = poly_desc.path
    # If the FC is inside a Feature Dataset, step up to the GDB level
    if arcpy.Describe(workspace).dataType == 'FeatureDataset': 
        workspace = arcpy.Describe(workspace).path
    
    edit = arcpy.da.Editor(workspace)
    edit.startEditing(False, True) # Multi-user mode off, Versioned data support on
    edit.startOperation()

    update_count = 0
    
    # 4. Use UpdateCursor to process each polygon
    poly_fields = ["OID@", "SHAPE@", f_from_str, f_to_str, f_from_int, f_to_int]
    
    with arcpy.da.UpdateCursor(poly_fc, poly_fields) as uc:
        for row in uc:
            oid, poly_geom = row[0], row[1]
            found_near = []

            # Find all points within 10 meters of this polygon
            for pt in points_list:
                dist = poly_geom.distanceTo(pt["geom"])
                if dist <= 10.0:  # Search radius set to 10 meters
                    found_near.append(pt)

            if found_near:
                # Logic: Sort found points by numeric chainage value (Ascending)
                found_near.sort(key=lambda x: x["ch_num"])
                
                # Minimum value is the START, Maximum value is the END
                start_node = found_near[0]
                end_node = found_near[-1]

                row[2] = start_node["ch_str"] # chainagefrom
                row[3] = end_node["ch_str"]   # chainageto
                row[4] = start_node["ch_num"] # chainagefromint
                row[5] = end_node["ch_num"]   # chainagetoint
                
                uc.updateRow(row)
                update_count += 1
                log_msg(f"Poly ID [{oid}]: Updated. {len(found_near)} nearby points found.")
            else:
                log_msg(f"Poly ID [{oid}]: Warning - No points found within 10 meters.")

    # 5. Save changes and close session
    edit.stopOperation()
    edit.stopEditing(True)
    log_msg("---------------------------------------------------------")
    log_msg(f"SUCCESS! Total {update_count} polygons updated.")

except Exception as e:
    arcpy.AddError(f"ERROR: {str(e)}")
    # If error occurs, stop editing without saving
    if 'edit' in locals() and edit.isEditing:
        edit.stopOperation()
        edit.stopEditing(False)
    log_msg("Process failed.")

finally:
    log_msg("Process completed.")
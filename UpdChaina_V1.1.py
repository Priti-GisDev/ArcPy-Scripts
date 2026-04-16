"""
Title: Automated Distance-Based Chainage Updater
Project: IDDP (Orange Gate) 
Description: 
    This tool automates chainage values (X+YYY format) in the Point Feature Class based on sequence and distance .
"""
import arcpy
import os
import datetime
import sys

# --- Logger Class ---
class Logger:
    def __init__(self, folder_path):
        file_name = f"UpdChainage_log-{datetime.datetime.now():%d_%m_%Y}.log"
        self.file = os.path.join(folder_path, file_name)

    def info(self, text):
        self.write_log(text, "INFO")
        arcpy.AddMessage(text)
        
    def error(self, text):
        self.write_log(text, "ERROR")
        arcpy.AddError(text)
        
    def warn(self, text):
        self.write_log(text, "WARNING")
        arcpy.AddWarning(text)
        
    def write_log(self, text, status):
        now = datetime.datetime.now()
        try:
            with open(self.file, 'a', encoding='utf-8') as writer:
                text_to_log = f"{now:%d-%m-%Y %H:%M:%S}\t{status}\t{text}\n"
                writer.write(text_to_log)
        except:
            pass

# Initialize Logger
log = Logger(os.path.expanduser(r"~\Downloads"))

def format_chainage(total_distance):
    km = int(total_distance // 1000)
    meters = int(total_distance % 1000)
    return f"{km}+{meters:03d}"

try:
    arcpy.env.overwriteOutput = True
    log.info("--- Process Started (Distance + Side Filter) ---")

    # Parameters
    chainage_layer = arcpy.GetParameterAsText(0)       
    increment_text = arcpy.GetParameterAsText(1)       
    tolerance = 5.0 
    side_field = "side"  # Ensure this field name matches your attribute table

    try:
        increment_val = float(increment_text)
    except ValueError:
        log.error("Error: Increment value must be a valid number!")
        sys.exit()

    # 1. Get the starting selected point and capture its "side" value
    selected_points = []
    # Added 'side' to the fields list
    fields = ['OID@', 'SHAPE@', 'chainagetotal', side_field]
    
    with arcpy.da.SearchCursor(chainage_layer, fields) as cursor:
        for row in cursor:
            selected_points.append(row)

    if len(selected_points) != 1:
        log.error("Error: Please select EXACTLY ONE starting point.")
        sys.exit()

    start_oid, current_geom, start_total, start_side = selected_points[0]
    current_total = float(start_total) if start_total is not None else 0.0

    log.info(f"START POINT: OID {start_oid} | Side: {start_side} | Initial Total: {current_total}")

    # 2. Get all other points, but ONLY if they have the same "side"
    arcpy.SelectLayerByAttribute_management(chainage_layer, "CLEAR_SELECTION")
    unvisited_points = {}
    
    # Filter by 'side' value to ignore points on the other side of the road/track
    with arcpy.da.SearchCursor(chainage_layer, ['OID@', 'SHAPE@', side_field]) as cursor:
        for row in cursor:
            oid, geom, side_val = row
            if oid != start_oid and side_val == start_side:
                unvisited_points[oid] = geom

    log.info(f"Found {len(unvisited_points)} other points with Side '{start_side}' to process.")

    updates_dict = {} 
    
    # 3. Find points sequentially based on distance (within the same side)
    while True:
        best_oid = None
        min_diff = 999999 

        for oid, geom in unvisited_points.items():
            distance = current_geom.distanceTo(geom)
            diff = abs(distance - increment_val)
            
            if diff < min_diff:
                min_diff = diff
                best_oid = oid

        # Only accept the point if it's within the distance tolerance
        if best_oid is not None and min_diff <= tolerance:
            current_total += increment_val
            updates_dict[best_oid] = current_total 

            current_geom = unvisited_points[best_oid]
            
            formatted = format_chainage(current_total)
            log.info(f"Sequence Match: OID {best_oid} | New Chainage: {formatted}")
            
            del unvisited_points[best_oid] 
        else:
            log.warn(f"Stopped: No further points found on side '{start_side}' within {tolerance}m of target distance.")
            break

    # 4. Apply updates to the attribute table
    if updates_dict:
        update_count = 0
        log.info(f"Writing updates for Side '{start_side}'...")
        with arcpy.da.UpdateCursor(chainage_layer, ['OID@', 'chainage', 'chainagetotal']) as update_cursor:
            for row in update_cursor:
                oid = row[0]
                if oid in updates_dict:
                    new_total = updates_dict[oid]
                    new_formatted = format_chainage(new_total)
                    
                    row[1] = new_formatted
                    row[2] = new_total
                    
                    update_cursor.updateRow(row)
                    update_count += 1
                    
        log.info(f"SUCCESS: {update_count} points updated on side '{start_side}'!")
    else:
        log.warn("No matching points found to update.")

except Exception as e:
    log.error(f"Execution Error: {str(e)}")

finally:
    log.info("--- Process Completed ---")
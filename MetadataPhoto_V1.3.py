"""
Title: Update Metadata of photos
Project: DPMS
Description: 
    This tool automates scans all tables for asset photos and creates an Excel report in the selected output folder. 
    It checks each individual photo's Metadata and udate in excel
"""
import os
import arcpy
import pandas as pd
from arcgis.gis import GIS
from arcgis.features import FeatureLayerCollection
import urllib3
import requests
import io
import datetime
import gc 
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- TABLES TO EXPLICITLY SKIP FOR PARENT LOOKUP ---
IGNORE_PARENT_LOOKUP = [
    'assetrelation wtp package',
    'assetrelation_watertreatmentplant'
]

# --- EXACT MAPPING DICTIONARY ---
PARENT_MAPPING = {
    'assetrelation_approachbridge': 'Approach Bridge',
    'assetrelation_approachchannel': 'Approach Channel',
    'assetrelation_adminblockandlabortaryitems': 'Admin Block And Labortary Items',
    'assetrelation_aerationfountain': 'Aeration Fountain',
    'assetrelation_breakpressuretank': 'Break Pressure Tank',
    'assetrelation_balancingtank': 'Balancing Tank',
    'assetrelation_bypass arrangement': 'Bypass Arrangement',
    'assetrelation_channel': 'Channel',
    'assetrelation_clariflocculator': 'Clariflocculator',
    'assetrelation_cmain': 'Connecting Main',
    'assetrelation_drainagearrangement': 'Drainage Arrangement',
    'assetrelation_dpipe': 'Distribution Pipe',
    'assetrelation_elevatedservicereservoir': 'ESR',
    'assetrelation_groundservicereservoir': 'GSR',
    'assetrelation_flocculator': 'Flocculator',
    'assetrelation_infiltration gallery': 'Infiltration Gallery',
    'assetrelation_inspectionwell': 'Inspection Well',
    'assetrelation_intakewell': 'Intake Well',
    'assetrelation_jackwell': 'Jack Well',
    'assetrelation_masterbalancingreservoir': 'MBR',
    'assetrelation_pontoon': 'Pontoon',
    'assetrelation_pump': 'Pump',
    'assetrelation_pwgm': 'Pure Water Gravity Main',
    'assetrelation_pwrm': 'Pure Water Rising Main',
    'assetrelation_purewatersumpandpumphouse': 'Pure Water Sump And Pump House',
    'assetrelation_rapidsandfilterandfilterhouse': 'Rapid Sand Filter And Filter House',
    'assetrelation_rwgm': 'Raw Water Gravity Main',
    'assetrelation_rwrm': 'Raw Water Rising Main',
    'assetrelation_solarpowerplant': 'Solar Power Plant',
    'assetrelation_sump': 'Sump',
    'assetrelation_supplywell': 'Supply Well',
    'assetrelation_tubesettler': 'Tube Settler',
    'assetrelation_well': 'Well',
    'assetrelation_washwatertank': 'Wash Water Tank',
    'assetrelation_raw water pumping machniary': 'Raw Water Pumping Machinary ',
    'assetrelation_pure water pumping machinary': 'Pure Water Pumping Machinary'
}

class Logger:
    def __init__(self, folder_path):
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        file_name = f"MetadataPhoto_Log-{datetime.datetime.now():%d_%m_%Y}.log"
        self.file = os.path.join(folder_path, file_name)
    
    def info(self, text):
        self.write_log(text, "INFO")
        arcpy.AddMessage(f"INFO: {text}")
    
    def error(self, text):
        self.write_log(text, "ERROR")
        arcpy.AddError(f"ERROR: {text}")
    
    def warn(self, text):
        self.write_log(text, "WARNING")
        arcpy.AddWarning(f"WARNING: {text}")
    
    def write_log(self, text, status):
        now = datetime.datetime.now()
        with open(self.file, 'a', encoding='utf-8') as writer:
            writer.write(f"{now:%d-%m-%Y %H:%M:%S}\t{status}\t{text}\n")

def format_arcgis_date(ms_value):
    if ms_value is None or ms_value == "" or ms_value < 0: return None
    try: return datetime.datetime.fromtimestamp(ms_value / 1000.0).strftime('%d-%m-%Y %H:%M:%S')
    except: return ms_value

def get_gps_from_bytes(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes))
        exif_data = image._getexif()
        if not exif_data: return None, None
        gps_info = {}
        for tag, value in exif_data.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                for t in value:
                    sub_decoded = GPSTAGS.get(t, t)
                    gps_info[sub_decoded] = value[t]
        if not gps_info: return None, None

        def convert_to_degrees(value):
            try:
                d, m, s = float(value[0]), float(value[1]), float(value[2])
                return d + (m / 60.0) + (s / 3600.0)
            except: return None

        lat = convert_to_degrees(gps_info.get("GPSLatitude"))
        lon = convert_to_degrees(gps_info.get("GPSLongitude"))
        if lat and gps_info.get("GPSLatitudeRef") == "S": lat = -lat
        if lon and gps_info.get("GPSLongitudeRef") == "W": lon = -lon
        return (str(round(lat, 6)), str(round(lon, 6))) if lat and lon else (None, None)
    except: return None, None

def fetch_attachment_metadata(att_item, base_data, session, item_url, token):
    oid = att_item['parent_oid']
    att_id = att_item['id']
    att_name = att_item['name']
    
    row_data = base_data.copy()
    row_data["att_name"] = str(att_name)
    lat, lon = None, None
    
    ext = str(att_name).lower().split('.')[-1]
    if ext in ['jpg', 'jpeg', 'tif', 'tiff']:
        try:
            att_url = f"{item_url}/{oid}/attachments/{att_id}"
            resp = session.get(att_url, params={'token': token}, verify=False, timeout=15)
            if resp.status_code == 200:
                lat, lon = get_gps_from_bytes(resp.content)
        except: pass
    
    row_data["photo_latitude"] = lat if lat else "N/A"
    row_data["photo_longitude"] = lon if lon else "N/A"
    row_data["geotag_status"] = "Yes" if lat and lon else "No"
    
    row_data["region"] = base_data.get("region", "")
    row_data["circle"] = base_data.get("circle", "")
    row_data["division"] = base_data.get("division", "")
    
    return row_data

def process_to_excel_sheets(service_url, portal_url, username, password, output_folder, include_list=None, exclude_list=None):
    log = Logger(output_folder)
    session = requests.Session() 
    
    try:
        start_time_total = datetime.datetime.now()
        log.info(f"Process Started at {start_time_total:%H:%M}")

        POTENTIAL_FIELDS = ["objectid", "schemename", "schemeid", "surveyordate", "guid", "globalid", "created_user", "created_date", "last_edited_user", "last_edited_date", "region", "circle", "division"] 
        DATE_FIELDS = ["surveyordate", "created_date", "last_edited_date"]
            
        gis = GIS(portal_url, username, password, verify_cert=False)
        token = gis._con.token
        flc = FeatureLayerCollection(service_url, gis=gis)
        
        excel_path = os.path.join(output_folder, "Asset_Photo_Report.xlsx")
        if os.path.exists(excel_path):
            os.remove(excel_path)

        all_items = flc.layers + flc.tables

        for item in all_items:
            table_name = item.properties.name
            table_name_lower = table_name.lower() 
            
            if include_list and table_name_lower not in include_list:
                continue

            if exclude_list and table_name_lower in exclude_list:
                log.info(f"Skipping Table (Excluded): {table_name}")
                continue

            try:
                if not getattr(item.properties, 'hasAttachments', False):
                    continue

                start_time_table = datetime.datetime.now()
                log.info(f"Processing Table: {table_name}....{start_time_table:%H:%M}")
                                
                available_fields = [f['name'] for f in item.properties.fields]
                current_table_fields = [f for f in available_fields if f.lower() in [rf.lower() for rf in POTENTIAL_FIELDS]]
                
                # --- CHECK IF IT IS A RELATION TABLE & GET PARENT NAME ---
                is_relation_table = False
                parent_target_name = None
                
                # Check IGNORE list first!
                if table_name_lower in IGNORE_PARENT_LOOKUP:
                    log.info(f"-> SKIP: '{table_name}'")
                    is_relation_table = False
                elif table_name_lower in PARENT_MAPPING:
                    is_relation_table = True
                    parent_target_name = PARENT_MAPPING[table_name_lower]
                elif table_name_lower.startswith("assetrelation_"):
                    is_relation_table = True
                    parent_target_name = table_name[14:] # Fallback just in case

                # --- FETCH PARENT DATA ---
                parent_lookup = {}
                if is_relation_table and parent_target_name:
                    
                    parent_layer = None
                    for lyr in flc.layers:
                        if lyr.properties.name.lower() == parent_target_name.lower() or lyr.properties.name.replace(" ", "").lower() == parent_target_name.replace(" ", "").lower():
                            parent_layer = lyr
                            log.info(f"-> Layer MATCH: '{lyr.properties.name}'")
                            break
                    
                    if parent_layer:
                        parent_fields = [f['name'] for f in parent_layer.properties.fields]
                        query_fields = []
                        for qf in ['globalid', 'region', 'circle', 'division']:
                            match = next((f for f in parent_fields if f.lower() == qf), None)
                            if match: query_fields.append(match)
                        
                        if len(query_fields) > 1:
                            try:
                                parent_res = parent_layer.query(where="1=1", out_fields=",".join(query_fields), return_geometry=False, return_all_records=True)
                                
                                globalid_fld = next((f for f in query_fields if f.lower() == 'globalid'), None)
                                reg_fld = next((f for f in query_fields if f.lower() == 'region'), None)
                                circ_fld = next((f for f in query_fields if f.lower() == 'circle'), None)
                                div_fld = next((f for f in query_fields if f.lower() == 'division'), None)
                                
                                if globalid_fld:
                                    for feat in parent_res.features:
                                        g_id = feat.attributes.get(globalid_fld)
                                        if g_id:
                                            g_id_clean = str(g_id).replace('{', '').replace('}', '').lower()
                                            parent_lookup[g_id_clean] = {
                                                "region": feat.attributes.get(reg_fld, "") if reg_fld else "",
                                                "circle": feat.attributes.get(circ_fld, "") if circ_fld else "",
                                                "division": feat.attributes.get(div_fld, "") if div_fld else ""
                                            }
                            except Exception as e:
                                log.error(f"-> Failed to load data from parent: {str(e)}")
                        else:
                            log.warn(f"-> Parent layer found, but missing region/circle/division fields.")
                    else:
                        log.warn(f"-> WARNING: Could not find Parent Layer '{parent_target_name}' in the service. Skipping fields.")

                # --- PROCESS ATTACHMENTS ---
                all_attachments = item.attachments.search(where="1=1", return_metadata=True)
                if not all_attachments:
                    log.warn(f"No attachments found for {table_name}, skipping.")
                    continue

                attachments_by_parent_oid = defaultdict(list)
                for a in all_attachments:
                    p_id = a.get('PARENTOBJECTID') or a.get('parentobjectid')
                    attachments_by_parent_oid[p_id].append({'id': a.get('ID') or a.get('id'), 'name': a.get('NAME')})

                relevant_oids = list(attachments_by_parent_oid.keys())
                parent_data_map = {}
                
                for i in range(0, len(relevant_oids), 500):
                    chunk = relevant_oids[i:i + 500]
                    try:
                        res = item.query(object_ids=",".join(map(str, chunk)), out_fields=",".join(current_table_fields), return_geometry=False)
                        for f in res.features:
                            attrs = f.attributes
                            oid = attrs.get("OBJECTID") or attrs.get("objectid")
                            base_data = {field: (format_arcgis_date(attrs.get(field)) if field.lower() in [df.lower() for df in DATE_FIELDS] else attrs.get(field)) for field in current_table_fields}
                            
                            # Initialize empty fields
                            if "region" not in base_data: base_data["region"] = ""
                            if "circle" not in base_data: base_data["circle"] = ""
                            if "division" not in base_data: base_data["division"] = ""
                            
                            # Try to match GUID with Parent Lookup ONLY if it's a relation table
                            if is_relation_table:
                                guid_val = None
                                for key, val in attrs.items():
                                    if key.lower() == 'guid' and val:
                                        guid_val = str(val).replace('{', '').replace('}', '').lower()
                                        break
                                        
                                if guid_val:
                                    if guid_val in parent_lookup:
                                        p_data = parent_lookup[guid_val]
                                        base_data["region"] = p_data.get("region", "")
                                        base_data["circle"] = p_data.get("circle", "")
                                        base_data["division"] = p_data.get("division", "")
                                    else:
                                        log.warn(f"   -> Row OID {oid}: Match NOT FOUND for GUID '{guid_val}'. Region/Circle/Division skipped.")

                            parent_data_map[oid] = base_data
                    except: continue

                tasks = []
                for oid, att_list in attachments_by_parent_oid.items():
                    base_data = parent_data_map.get(oid)
                    if not base_data: continue
                    for att in att_list:
                        tasks.append({'parent_oid': oid, 'id': att['id'], 'name': att['name'], 'base_data': base_data})

                table_rows = []
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(fetch_attachment_metadata, t, t['base_data'], session, item.url, token) for t in tasks]
                    for future in futures:
                        table_rows.append(future.result())

                if table_rows:
                    df = pd.DataFrame(table_rows)
                    
                    mode = 'a' if os.path.exists(excel_path) else 'w'
                    with pd.ExcelWriter(excel_path, engine='openpyxl', mode=mode, if_sheet_exists='replace' if mode=='a' else None) as writer:
                        df.to_excel(writer, sheet_name=table_name[:31], index=False)

                del table_rows, parent_data_map, tasks, all_attachments, attachments_by_parent_oid, parent_lookup
                gc.collect() 

                end_time_table = datetime.datetime.now()
                log.info(f"Finished Table: {table_name} at {end_time_table:%H:%M}...")

            except Exception as e:
                log.error(f"Failed to process table {table_name}: {str(e)}")
                continue

        log.info(f"Process Completed. Total Time: {datetime.datetime.now() - start_time_total}")

    except Exception as e:
        log.error(f"Critical System Error: {str(e)}")

def main():
    service_url = arcpy.GetParameterAsText(0).strip()
    portal_url = arcpy.GetParameterAsText(1).strip()
    username = arcpy.GetParameterAsText(2).strip()
    password = arcpy.GetParameterAsText(3).strip()
    output_folder = arcpy.GetParameterAsText(4).strip()
    include_str = arcpy.GetParameterAsText(5).strip() 
    exclude_str = arcpy.GetParameterAsText(6).strip() 
    
    include_list = [x.strip().lower() for x in include_str.split(',')] if include_str else None
    exclude_list = [x.strip().lower() for x in exclude_str.split(',')] if exclude_str else None
    
    if not all([service_url, portal_url, username, password, output_folder]): 
        arcpy.AddError("Error: Basic parameters are required.")
        return
        
    process_to_excel_sheets(service_url, portal_url, username, password, output_folder, include_list, exclude_list)

if __name__ == "__main__":
    main()
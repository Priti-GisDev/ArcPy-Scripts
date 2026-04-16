"""
Title: Check Domain Values
Project: HDOT 2025
Description: Domain: Check all Layes Domain value as per input or Template GDB
    
"""
import arcpy
import os
import datetime

class Logger:
    def __init__(self, folder_path):
        file_name = f"CheckDomain_log-{datetime.datetime.now():%d_%m_%Y}.log"
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
        except: pass

def clean_string(val):
    """
    Removes quotes, strips whitespace, and lowercases the string for matching.
    """
    if val is None:
        return ""
    cleaned = str(val).replace('"', '').replace("'", "").strip().lower()
    return cleaned

log = Logger(os.path.expanduser("~\\Downloads"))
Input_GDB = arcpy.GetParameterAsText(0) 

if not Input_GDB:
    log.error("No Input GDB provided.")
else:
    arcpy.env.workspace = Input_GDB
    arcpy.env.overwriteOutput = True

    try:
        domain_map = {}
        for domain in arcpy.da.ListDomains(Input_GDB):
            if domain.domainType == 'CodedValue':
                cv = domain.codedValues 
                lookup = {}
                for code, desc in cv.items():
                    lookup[clean_string(code)] = code
                    lookup[clean_string(desc)] = code
                
                domain_map[domain.name] = {
                    'type': 'Coded',
                    'actual_codes': cv.keys(),
                    'lookup_map': lookup
                }
            elif domain.domainType == 'Range':
                domain_map[domain.name] = {
                    'type': 'Range', 
                    'min': domain.range[0], 
                    'max': domain.range[1]
                }

        fcs = arcpy.ListFeatureClasses()
        for ds in arcpy.ListDatasets(feature_type='feature'):
            fcs.extend([os.path.join(ds, fc) for fc in arcpy.ListFeatureClasses(feature_dataset=ds)])

        for fc in fcs:
            fields = arcpy.ListFields(fc)
            fields_with_domains = [f for f in fields if f.domain and f.domain in domain_map]
            
            if not fields_with_domains:
                continue

            log.info(f"Checking FC: {os.path.basename(fc)}")

            field_names_list = [f.name.lower() for f in fields]
            if "Domain_error" not in field_names_list:
                arcpy.AddField_management(fc, "Domain_error", "TEXT", field_length=500)

            field_names = [f.name for f in fields_with_domains]
            cursor_fields = field_names + ["Domain_error"]
            
            with arcpy.da.UpdateCursor(fc, cursor_fields) as cursor:
                for row in cursor:
                    invalid_fields = []
                    row_list = list(row)
                    row_was_modified = False
                    
                    for i, f_name in enumerate(field_names):
                        val = row_list[i]
                        if val is None or val == "": continue
                        
                        d_name = fields_with_domains[i].domain
                        d_info = domain_map[d_name]
                        
                        if d_info['type'] == 'Coded':
                            if val in d_info['actual_codes']:
                                continue
                            
                            cleaned_val = clean_string(val)
                            
                            if cleaned_val in d_info['lookup_map']:
                                row_list[i] = d_info['lookup_map'][cleaned_val]
                                row_was_modified = True
                            else:
                                invalid_fields.append(f_name)

                        elif d_info['type'] == 'Range':
                            try:
                                num_val = float(val)
                                if not (d_info['min'] <= num_val <= d_info['max']):
                                    invalid_fields.append(f_name)
                            except:
                                invalid_fields.append(f_name)
                    
                    if invalid_fields:
                        row_list[-1] = ", ".join(invalid_fields)
                    else:
                        row_list[-1] = None
                    
                    cursor.updateRow(row_list)

        log.info("Process Completed. Data cleaned and errors updated.")

    except Exception as e:
        log.error(f"An error occurred: {str(e)}")
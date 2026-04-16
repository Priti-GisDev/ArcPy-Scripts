import arcpy
import os
import datetime

class Logger:
    def __init__(self, folder_path):
        file_name = "MrgCodeGDB-log-{0}.log".format(datetime.datetime.now().strftime('%d_%m_%Y'))
        self.file = os.path.join(folder_path, file_name)

    def info(self, text):
        self.writeLog(text, "INFO")

    def error(self, text, filepath=None):
        self.writeLog(text, "ERROR", filepath)

    def warn(self, text):
        self.writeLog(text, "WARNING")

    def writeLog(self, text, status, filepath=None):
        now = datetime.datetime.now()
        with open(self.file, 'a') as log_file:
            timestamp = now.strftime("%d-%m-%Y %H:%M:%S") + "," + str(now.microsecond)[:3]
            log_line = "{0}\t{1}\t".format(timestamp, status)
            if filepath:
                log_line += "In File: {0}\t".format(filepath)
            log_line += text + "\n"
            log_file.write(log_line)

# Input/output paths from ArcGIS tool parameters
Input_Folder = arcpy.GetParameterAsText(0)
Output_Folder = arcpy.GetParameterAsText(1)

# Logger
log_folder = os.path.expanduser("~\\Downloads")
log = Logger(log_folder)
log.info("Processing started.")

# Print statement for console output
print("Processing started.")

merged_gdb_name = "Merged.gdb"
merged_gdb_path = os.path.join(Output_Folder, merged_gdb_name)

# Create merged GDB if it doesn't exist
if not arcpy.Exists(merged_gdb_path):
    try:
        arcpy.CreateFileGDB_management(Output_Folder, merged_gdb_name)
        log.info("Created merged GDB: " + merged_gdb_path)
        print("Created merged GDB: " + merged_gdb_path)
    except Exception as e:
        log.error("Failed to create output GDB", merged_gdb_path)
        print("Failed to create output GDB: " + merged_gdb_path)
        raise e

def skip_prefix(name):
    return name[3:] if len(name) > 3 else name

total_count = 0  # To track the total count of features across all feature classes

first_gdb = None  # To track the first GDB encountered

# Walk through folder structure
for root, dirs, files in os.walk(Input_Folder):
    for dir in dirs:
        if dir.lower().endswith(".gdb"):
            gdb_path = os.path.join(root, dir)
            arcpy.env.workspace = gdb_path
            log.info("Found geodatabase: " + gdb_path)
            print("Found geodatabase: " + gdb_path)

            # Set first GDB
            if first_gdb is None:
                first_gdb = gdb_path

            datasets = arcpy.ListDatasets(feature_type='feature') or []
            datasets.append('')  # Include root dataset

            for ds in datasets:
                ds_path = os.path.join(gdb_path, ds) if ds else gdb_path
                feature_classes = arcpy.ListFeatureClasses(feature_dataset=ds)

                if not feature_classes:
                    log.warn("No feature classes in: " + ds_path)
                    print("No feature classes in: " + ds_path)
                    continue

                for fc in feature_classes:
                    fc_input_path = os.path.join(ds_path, fc)
                    new_ds_name = skip_prefix(ds) if ds else "GENERAL"
                    new_fc_name = skip_prefix(fc)

                    out_dataset_path = os.path.join(merged_gdb_path, new_ds_name)
                    out_fc_path = os.path.join(out_dataset_path, new_fc_name)

                    # Create dataset in merged GDB if it doesn't exist
                    if not arcpy.Exists(out_dataset_path):
                        try:
                            sr = arcpy.Describe(fc_input_path).spatialReference
                            arcpy.CreateFeatureDataset_management(merged_gdb_path, new_ds_name, sr)
                            log.info("Created dataset: " + new_ds_name)
                            print("Created dataset: " + new_ds_name)
                        except Exception as e:
                            log.error("Failed to create dataset: " + new_ds_name, gdb_path)
                            print("Failed to create dataset: " + new_ds_name)
                            continue

                    # Create feature class in merged GDB based on the first GDB structure
                    if not arcpy.Exists(out_fc_path):
                        try:
                            desc = arcpy.Describe(fc_input_path)
                            arcpy.CreateFeatureclass_management(
                                out_dataset_path,
                                new_fc_name,
                                geometry_type=desc.shapeType,
                                spatial_reference=desc.spatialReference,
                                template=fc_input_path
                            )
                            log.info("Created feature class: {0}\\{1}".format(new_ds_name, new_fc_name))
                            print("Created feature class: " + new_ds_name + "\\" + new_fc_name)

                            # Ensure fields from the first GDB are copied over
                            if first_gdb:
                                first_gdb_fc = os.path.join(first_gdb, new_ds_name, new_fc_name) if new_ds_name else os.path.join(first_gdb, new_fc_name)
                                if arcpy.Exists(first_gdb_fc):
                                    # List all fields and add them to the new feature class if missing
                                    fields = arcpy.ListFields(first_gdb_fc)
                                    for field in fields:
                                        try:
                                            if field.name not in [f.name for f in arcpy.ListFields(out_fc_path)]:
                                                arcpy.AddField_management(out_fc_path, field.name, field.type, field.precision, field.scale, field.length)
                                                log.info("Added field: {0} to {1}".format(field.name, new_fc_name))
                                                print("Added field: " + field.name + " to " + new_fc_name)
                                        except Exception as e:
                                            log.error("Error adding field: " + field.name, first_gdb_fc)
                                            print("Error adding field: " + field.name)
                        except Exception as e:
                            log.error("Failed to create feature class: " + new_fc_name, fc_input_path)
                            print("Failed to create feature class: " + new_fc_name)
                            continue

                    try:
                        # Perform the append operation
                        arcpy.Append_management(fc_input_path, out_fc_path, "NO_TEST")
                        
                        # Count features and add to total count
                        count = int(arcpy.GetCount_management(fc_input_path)[0])
                        total_count += count

                        log.info("Dataset: {0} - FeatureClass: {1}, Count: {2}".format(ds if ds else "Root", fc, count))
                        print("Dataset: " + (ds if ds else "Root") + " - FeatureClass: " + fc + ", Count: " + str(count))
                    except Exception as e:
                        log.error("Failed to append or count: " + new_fc_name, fc_input_path)
                        print("Failed to append or count: " + new_fc_name)

# Log total features processed
log.info("Total number of features merged: " + str(total_count))
print("Total number of features merged: " + str(total_count))

log.info("Processing completed.")
print("Processing completed.")

using System;
using System.IO;
using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json;
using System.Linq;
using Newtonsoft.Json.Linq;
using LogCenter;

public class LogUtilSdk : MonoBehaviour
{
    private static string logFilePath;
    private static ConfigManager config;

    public class DataLogList
    {
        public List<DataLogSdk> logs = new List<DataLogSdk>();
    }
    public static void SaveLogToJson(DataLogSdk DataLogSdk)
    {

        string folderPath = Path.Combine(Application.persistentDataPath, "data_logs");

        if (!Directory.Exists(folderPath))
        {
            Directory.CreateDirectory(folderPath);
        }

        string logFilePath = Path.Combine(folderPath, "data_logs.json");

        List<DataLogSdk> logList = new List<DataLogSdk>();

        if (File.Exists(logFilePath))
        {
            if (isJsonCorrupted(logFilePath))
            {
                File.WriteAllText(logFilePath, "[]");
            }
            else
            {
                string existingJson = File.ReadAllText(logFilePath);
                if (!string.IsNullOrWhiteSpace(existingJson))
                {
                    logList = JsonConvert.DeserializeObject<List<DataLogSdk>>(existingJson);
                }
            }
        }

        DataLogSdk.timestamp = DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ssZ");
        logList.Add(DataLogSdk);

        string newJson = JsonConvert.SerializeObject(logList, Formatting.Indented); // 'true' for pretty-print
        File.WriteAllText(logFilePath, newJson);


        Debug.Log("Log saved at " + logFilePath);
    }
    public static IEnumerator GetDatalogFromJsonCoroutine(Action<DataLogSdk> onComplete)
    {
        config = new();
        DataLogSdk DataLogSdk = new DataLogSdk();
        DataLogSdk.project_id = config.GetValue("DataLog", "ProjectId", " ");
        DataLogSdk.tags = config.GetValue("DataLog", "Tags", " ").Split(new char[] { ',' }).Select(t => t.Trim()).Where(t => !string.IsNullOrEmpty(t)).ToList();
        DataLogSdk.status = "success";
        onComplete?.Invoke(DataLogSdk);
        yield return null;
    }

    static bool isJsonCorrupted(string filePath)
    {
        try
        {
            string jsonContent = File.ReadAllText(filePath);
            JToken.Parse(jsonContent);
            return false;
        }
        catch (JsonReaderException ex)
        {
            Console.WriteLine($"JSON file corruption detected: {ex.Message}");
            return true;
        }
        catch (IOException ex)
        {
            Console.WriteLine($"File reading error: {ex.Message}");
            return true;
        }
    }

}

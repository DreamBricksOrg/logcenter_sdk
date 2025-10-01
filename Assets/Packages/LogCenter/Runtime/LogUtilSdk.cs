using System;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json;

public class LogUtilSdk : MonoBehaviour
{
    private static string logFilePath;
    private static ConfigManagerSdk config;

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
            string existingJson = File.ReadAllText(logFilePath);
            if (!string.IsNullOrWhiteSpace(existingJson))
            {
                logList = JsonConvert.DeserializeObject<List<DataLogSdk>>(existingJson);
            }
        }

        DataLogSdk.timestamp = DateTime.Now;
        logList.Add(DataLogSdk);

        string newJson = JsonConvert.SerializeObject(logList, Formatting.Indented); // 'true' for pretty-print
        File.WriteAllText(logFilePath, newJson);


        Debug.Log("Log saved at " + logFilePath);
    }
    public static IEnumerator GetDatalogFromJsonCoroutine(Action<DataLogSdk> onComplete)
    {
        config = new();
        DataLogSdk DataLogSdk = new DataLogSdk();
        DataLogSdk.id = config.GetValue("Json", "id");
        DataLogSdk.project = config.GetValue("Json", "project");
        onComplete?.Invoke(DataLogSdk);
        yield return null;
    }
}

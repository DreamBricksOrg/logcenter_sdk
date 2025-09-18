using System;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json;

public class LogUtil : MonoBehaviour
{
    private static string logFilePath;
    public class DataLogList
    {
        public List<DataLog> logs = new List<DataLog>();
    }
    public static void SaveLogToJson(DataLog dataLog)
    {
        string folderPath = Path.Combine(Application.persistentDataPath, "data_logs");

        if (!Directory.Exists(folderPath))
        {
            Directory.CreateDirectory(folderPath);
        }

        string logFilePath = Path.Combine(folderPath, "data_logs.json");
        
        List<DataLog> logList = new List<DataLog>();

        if (File.Exists(logFilePath))
        {
            string existingJson = File.ReadAllText(logFilePath);
            if (!string.IsNullOrWhiteSpace(existingJson))
            {
                logList = JsonConvert.DeserializeObject<List<DataLog>>(existingJson);
            }
        }

        dataLog.timestamp = DateTime.Now;
        logList.Add(dataLog);

        string newJson = JsonConvert.SerializeObject(logList,Formatting.Indented); // 'true' for pretty-print
        File.WriteAllText(logFilePath, newJson);


        Debug.Log("Log saved at " + logFilePath);
    }
    public static IEnumerator GetDatalogFromJsonCoroutine(Action<DataLog> onComplete)
    {
        string jsonFileName = "datalog.json";
        string filePath = Path.Combine(Application.streamingAssetsPath, jsonFileName);

#if UNITY_ANDROID
        string uri = filePath;
#else
        string uri = "file://" + filePath;
#endif

        UnityWebRequest request = UnityWebRequest.Get(uri);
        yield return request.SendWebRequest();

        if (request.result != UnityWebRequest.Result.Success)
        {
            Debug.LogError("Failed to read datalog.json: " + request.error);
            onComplete?.Invoke(null);
        }
        else
        {
            string json = request.downloadHandler.text;
            DataLog dataLog = JsonConvert.DeserializeObject<DataLog>(json);
            onComplete?.Invoke(dataLog);
        }
    }
}

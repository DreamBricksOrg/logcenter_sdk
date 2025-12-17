using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using UnityEngine;
using UnityEngine.Networking;
using Newtonsoft.Json;
using LogCenter;
public class LogCenterV2Uploader : MonoBehaviour
{
    public string outputFolder;
    public int timeInMinutesAlive = 30;
    private DateTime timer;
    private string outputPath;
    private string backupPath;
    private string datalogFolder;
    public int checkIntervalSeconds;
    private string uploadURL;
    private string apiKey;
    private ConfigManager config;

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    private void Awake()
    {
        config = new();
        uploadURL = config.GetValue("DataLog", "Url", " ");
        apiKey = config.GetValue("DataLog", "ApiKey", " ");
        timer = DateTime.Now.AddMinutes(timeInMinutesAlive);
    }
    void Start()
    {
        datalogFolder = Path.Combine(Application.persistentDataPath, outputFolder);
        CheckIfDirectoryExists(datalogFolder);
        outputPath = EnsureJsonFilesExist(datalogFolder, "data_logs.json");
        backupPath = EnsureJsonFilesExist(datalogFolder, "data_logs_backup.json");
        StartCoroutine(Worker());
    }

    void Update()
    {
        if (DateTime.Now > timer)
        {
            timer = DateTime.Now.AddMinutes(timeInMinutesAlive);
            bool sendSuccess = false;
            DataLogSdk dataLog = new DataLogSdk();
            dataLog.message = "ALIVE";
            dataLog.level = "INFO";
            dataLog.project_id = config.GetValue("DataLog", "ProjectId");
            LogUtilSdk.SaveLogToJson(dataLog);
            StartCoroutine(SendData(dataLog, success => sendSuccess = success));
        }
    }

    IEnumerator Worker()
    {
        while (true)
        {
            yield return new WaitForSeconds(checkIntervalSeconds);

            // check if internet is available
            // if (CheckForInternetConnection())
            // {
            //     Debug.Log("no internet available");
            //     continue;
            // }

            if (File.Exists(outputPath))
            {
                // L� todas as linhas do arquivo Json
                string allLines = File.ReadAllText(outputPath);
                List<DataLogSdk> data = JsonConvert.DeserializeObject<List<DataLogSdk>>(allLines);

                // Verifica se h� linhas de dados no arquivo CSV
                if (data == null || data?.Count == 0)
                {
                    Debug.Log("O arquivo Json est� vazio: " + outputPath);
                    continue;
                }

                List<DataLogSdk> updatedData = new List<DataLogSdk>(data);
                File.WriteAllText(backupPath, JsonConvert.SerializeObject(updatedData, Formatting.Indented));
                for (int i = 0; i < updatedData.Count; i++)
                {
                    DataLogSdk updatedDataJson = updatedData[i];
                    bool sendSuccess = false;

                    Debug.Log(string.Format("processing line '{0}' de '{1}' ", i + 1, updatedData.Count));

                    yield return StartCoroutine(SendData(updatedDataJson, success => sendSuccess = success));

                    if (sendSuccess)
                    {
                        // Remova a linha do arquivo original
                        updatedData.RemoveAt(i);

                        // Reduza o valor de i para lidar com a remo��o da linha
                        i--;
                    }
                    else
                    {
                        Debug.LogWarning(string.Format("Falha ao enviar a linha '{0}', n�o ser� removida.", updatedDataJson));
                    }
                }

                // Escreva as linhas restantes de volta no arquivo Json com o cabe�alho
                if (updatedData.Count > 0)
                {
                    string stringJson = JsonConvert.SerializeObject(updatedData, Formatting.Indented);
                    File.WriteAllText(outputPath, stringJson);
                }
                else
                {
                    File.WriteAllText(outputPath, "");
                }
            }
        }
    }

    virtual protected IEnumerator SendData(DataLogSdk dataLog, Action<bool> callback)
    {

        string jsonData = JsonConvert.SerializeObject(dataLog, Formatting.Indented);
        //form.AddField("Json", jsonData);

        // Crie uma requisicao UnityWebRequest para enviar o arquivo
        using (UnityWebRequest www = UnityWebRequest.Post(uploadURL, jsonData, "application/json"))
        {
            www.SetRequestHeader("X_API_Key", apiKey);
            Debug.Log("API key header: " + www.GetRequestHeader("X_API_Key"));
            yield return www.SendWebRequest(); // Envie a requisicao

            if (www.result == UnityWebRequest.Result.Success)
            {
                Debug.Log(string.Format("Arquivo '{0}' enviado com sucesso!", dataLog));
                callback(true);
            }
            else
            {
                Debug.Log(string.Format("Erro ao enviar o arquivo '{0}': {1}", dataLog, www.error));
                callback(false);
            }
        }
    }

    public static bool CheckForInternetConnection(int timeoutMs = 2000)
    {
        try
        {
            string url = "https://dbutils.ddns.net";

            var request = (HttpWebRequest)WebRequest.Create(url);
            request.KeepAlive = false;
            request.Timeout = timeoutMs;
            using (var response = (HttpWebResponse)request.GetResponse())
                return true;
        }
        catch
        {
            return false;
        }
    }

    public static void CheckIfDirectoryExists(string path)
    {
        bool exists = System.IO.Directory.Exists(path);

        if (!exists)
        {
            System.IO.Directory.CreateDirectory(path);
        }
    }

    public static string EnsureJsonFilesExist(string directory, string file)
    {
        string filePath = Path.Combine(directory, file);

        // Verifica se o arquivo data_logs.json existe, se n�o existir, cria
        if (!File.Exists(filePath))
        {
            File.WriteAllText(filePath, "");
        }

        return filePath;
    }
}

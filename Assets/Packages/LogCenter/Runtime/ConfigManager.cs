using System.Collections.Generic;
using System;
using System.IO;
using UnityEngine;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Networking;
#endif

public class ConfigManager
{
    private Dictionary<string, Dictionary<string, string>> configData;
    private string fileName;
    private string persistentPath;

    public ConfigManager(string fileName = "config.ini")
    {
        this.fileName = fileName;
        configData = new Dictionary<string, Dictionary<string, string>>();
        persistentPath = Path.Combine(Application.persistentDataPath, fileName);

        if (File.Exists(persistentPath))
        {
            string[] lines = File.ReadAllLines(persistentPath);
            ParseLines(lines);
        }
        else
        {
            string[] lines = LoadFromStreamingAssetsSync();
            if (lines != null)
            {
                ParseLines(lines);
                SaveConfig();
            }
            else
            {
                Debug.LogError("Arquivo config.ini não encontrado!");
            }
        }
    }

    private string[] LoadFromStreamingAssetsSync()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        string path = Path.Combine(Application.streamingAssetsPath, fileName);
        UnityWebRequest www = UnityWebRequest.Get(path);
        var operation = www.SendWebRequest();
        while (!operation.isDone) { } // Espera síncrona (bloqueia o thread principal)

        if (www.result != UnityWebRequest.Result.Success)
        {
            Debug.LogError("Erro ao ler StreamingAssets no Android: " + www.error);
            return null;
        }

        return www.downloadHandler.text.Split('\n');
#else
        string path = Path.Combine(Application.streamingAssetsPath, fileName);
        if (!File.Exists(path))
        {
            Debug.LogError("Arquivo não encontrado em StreamingAssets!");
            return null;
        }

        return File.ReadAllLines(path);
#endif
    }

    private void ParseLines(string[] lines)
    {
        string currentSection = "";
        foreach (var rawLine in lines)
        {
            string line = rawLine.Trim();
            if (string.IsNullOrEmpty(line) || line.StartsWith(";") || line.StartsWith("#"))
                continue;

            if (line.StartsWith("[") && line.EndsWith("]"))
            {
                currentSection = line.Substring(1, line.Length - 2).Trim();
                if (!configData.ContainsKey(currentSection))
                    configData[currentSection] = new Dictionary<string, string>();
            }
            else if (line.Contains("="))
            {
                var split = line.Split(new char[] { '=' }, 2);
                string key = split[0].Trim();
                string value = split[1].Trim();
                if (!string.IsNullOrEmpty(currentSection))
                    configData[currentSection][key] = value;
            }
        }
    }

    public string GetValue(string section, string key, string defaultValue = "")
    {
        bool modified = false;
        if (!configData.ContainsKey(section))
        {
            configData[section] = new Dictionary<string, string>();
            modified = true;
        }

        if (!configData[section].ContainsKey(key))
        {
            configData[section][key] = defaultValue;
            modified = true;
        }

        if (modified)
            SaveConfig();

        return configData[section][key];
    }

    public void SetValue(string section, string key, string value)
    {
        if (!configData.ContainsKey(section))
            configData[section] = new Dictionary<string, string>();
        configData[section][key] = value;
    }

    public bool SaveConfig()
    {
        try
        {
            string dir = Path.GetDirectoryName(persistentPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                Directory.CreateDirectory(dir);

            List<string> lines = new List<string>();
            foreach (var section in configData)
            {
                lines.Add($"[{section.Key}]");
                foreach (var kvp in section.Value)
                    lines.Add($"{kvp.Key}={kvp.Value}");
                lines.Add("");
            }

            File.WriteAllLines(persistentPath, lines);

            if (File.Exists(persistentPath))
            {
                var fi = new FileInfo(persistentPath);
                return fi.Length >= 0;
            }
            return false;
        }
        catch (Exception ex)
        {
            Debug.LogError($"Falha ao salvar config: {ex.Message}");
            return false;
        }
    }

    public List<string> GetAllSections()
    {
        return new List<string>(configData.Keys);
    }

    public Dictionary<string, string> GetSection(string section)
    {
        if (configData.ContainsKey(section))
            return configData[section];
        return new Dictionary<string, string>();
    }

}
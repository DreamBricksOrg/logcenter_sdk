using UnityEngine;
using UnityEditor;
using System.IO;

[InitializeOnLoad]
public static class PackageAutoInstaller
{
    private const string MarkerFolder = "Library";
    private const string MarkerFile = "MyPackage_InstalledVersion.txt";

    static PackageAutoInstaller()
    {
        string markerPath = Path.Combine(MarkerFolder, MarkerFile);

        string currentVersion = GetPackageVersion();
        string installedVersion = File.Exists(markerPath)
            ? File.ReadAllText(markerPath)
            : "";

        // Version has changed → run installer
        if (currentVersion != installedVersion)
        {
            InstallFiles();

            Directory.CreateDirectory(MarkerFolder);
            File.WriteAllText(markerPath, currentVersion);
        }
    }

    private static string GetPackageVersion()
    {
        string packageJson = "Packages/com.dreambricks.logcentersdk/package.json";
        if (!File.Exists(packageJson))
            return "0.0.0";

        string json = File.ReadAllText(packageJson);
        return JsonUtility.FromJson<PackageVersionWrapper>(json).version;
    }

    private static void InstallFiles()
    {
        string source = "Packages/com.dreambricks.logcentersdk/Runtime/";
        string target = "Assets/logcentersdk/Scripts";

        foreach (string file in Directory.GetFiles(source, "*.cs", SearchOption.AllDirectories))
        {
            string relative = file.Replace(source, "").TrimStart(Path.DirectorySeparatorChar);
            string targetFile = Path.Combine(target, relative);

            Directory.CreateDirectory(Path.GetDirectoryName(targetFile));

            // ✔ Prevent overwriting user's modified files
            if (File.Exists(targetFile)) continue;

            File.Copy(file, targetFile);
        }

        AssetDatabase.Refresh();
        Debug.Log("✔ MyPackage scripts updated in Assets/");
    }

    // Helps Unity deserialize the version field from package.json
    private class PackageVersionWrapper
    {
        public string version;
    }
}

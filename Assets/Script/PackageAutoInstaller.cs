// using UnityEngine;
// using UnityEditor;
// using System.IO;
// using System.Text;
// using System.Text.RegularExpressions;

// [InitializeOnLoad]
// public static class PackageAutoInstaller
// {
//     private const string MarkerFolder = "Library";
//     private const string MarkerFile = "MyPackage_InstalledVersion.txt";
//     private const string NamespaceToApply = "LogCenterSDK.Generated";

//     static PackageAutoInstaller()
//     {
//         string markerPath = Path.Combine(MarkerFolder, MarkerFile);

//         string currentVersion = GetPackageVersion();
//         string installedVersion = File.Exists(markerPath)
//             ? File.ReadAllText(markerPath)
//             : "";

//         if (currentVersion != installedVersion)
//         {
//             InstallFiles();

//             Directory.CreateDirectory(MarkerFolder);
//             File.WriteAllText(markerPath, currentVersion);
//         }
//     }

//     private static string GetPackageVersion()
//     {
//         string packageJson = "Packages/com.dreambricks.logcentersdk/package.json";
//         if (!File.Exists(packageJson))
//             return "0.0.0";

//         string json = File.ReadAllText(packageJson);
//         return JsonUtility.FromJson<PackageVersionWrapper>(json).version;
//     }

//     private static void InstallFiles()
//     {
//         string source = "Packages/com.dreambricks.logcentersdk/Runtime/";
//         string target = "Assets/logcentersdk/Scripts";

//         foreach (string file in Directory.GetFiles(source, "*.cs", SearchOption.AllDirectories))
//         {
//             string relative = file.Replace(source, "").TrimStart(Path.DirectorySeparatorChar);
//             string targetFile = Path.Combine(target, relative);

//             Directory.CreateDirectory(Path.GetDirectoryName(targetFile));

//             // ❗ Skip existing files to avoid overwriting user changes
//             if (File.Exists(targetFile)) continue;

//             // Read script
//             string script = File.ReadAllText(file);

//             // Apply namespace if needed
//             script = ApplySafeNamespace(script, NamespaceToApply);

//             File.WriteAllText(targetFile, script, Encoding.UTF8);
//         }

//         AssetDatabase.Refresh();
//         Debug.Log("✔ MyPackage scripts updated in Assets/ with namespace applied");
//     }

//     private static string ApplySafeNamespace(string script, string namespaceName)
//     {
//         // Already has a namespace?
//         if (Regex.IsMatch(script, @"namespace\s+\w"))
//             return script;

//         // Contains partial class? (Avoid breaking multi-file definitions)
//         if (Regex.IsMatch(script, @"partial\s+class\s+\w+"))
//             return script;

//         // Get all content after the last using
//         Match lastUsing = Regex.Match(script, @"(^using .+?;\s*)+", RegexOptions.Singleline);
//         if (!lastUsing.Success)
//             return script;

//         string usings = lastUsing.Value;
//         string rest = script.Substring(usings.Length);

//         // Apply namespace wrapping
//         StringBuilder sb = new StringBuilder();
//         sb.Append(usings);
//         sb.AppendLine();
//         sb.AppendLine($"namespace {namespaceName}");
//         sb.AppendLine("{");
//         sb.AppendLine(rest);
//         sb.AppendLine("}");

//         return sb.ToString();
//     }

//     private class PackageVersionWrapper
//     {
//         public string version;
//     }
// }

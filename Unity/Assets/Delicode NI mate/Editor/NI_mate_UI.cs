/* Original code by Delicode Ltd (www.delicode.com) */
/* All modifications are allowed, but we encourage  */
/* sharing any beneficial modifications at the NI   */
/* mate forums (forum.ni-mate.com).	    			*/

using UnityEngine;
using UnityEditor;
using System.Collections.Generic;
using System.IO;

[CustomEditor(typeof(NImateReceiver))]
public class NI_mate_UI : Editor
{	
	public override void OnInspectorGUI () {
		NImateReceiver ni = (NImateReceiver) target;
		
		GUI.enabled = !Application.isPlaying;
		ni.OSCport = EditorGUILayout.IntField(new GUIContent("Port", "Receive OSC on this port, must match the Full Skeleton port in NI mate!"), ni.OSCport);
		GUI.enabled = true;
		
		ni.keepOriginalRotations = EditorGUILayout.Toggle(new GUIContent("Add to original rotations", "Add received rotation data to the original rotations"), ni.keepOriginalRotations);
		ni.useRootRotation = EditorGUILayout.Toggle(new GUIContent("Use root rotation", "Use the root transform rotation before adding the received rotation"), ni.useRootRotation);
		
		EditorGUILayout.BeginHorizontal();
		ni.startNImate = EditorGUILayout.Toggle(new GUIContent("Start NI mate", "Start NI mate when the game starts using the specified profile file"), ni.startNImate);
		
		GUI.enabled = ni.startNImate;
			string assets_path = Application.dataPath;
	        string[] aFilePaths = Directory.GetFiles(assets_path, "*.nimate", SearchOption.AllDirectories);
			
			List<string> profiles = new List<string>();
			
			int profile_index = 0;
			
			for(int i=0; i<aFilePaths.Length; i++) {
				string profile_name = aFilePaths[i].Substring(assets_path.Length+1);
				profiles.Add(profile_name);
				
				if(profile_name == ni.profileFile)
					profile_index = profiles.Count-1;
			}
			
			string[] profile_array = profiles.ToArray();
			
			if(profile_array.Length == 0) {
				EditorGUILayout.LabelField("No profile files found!");
				ni.profileFile = "";
			}
			else {
				profile_index = EditorGUILayout.Popup("", profile_index, profile_array);
				ni.profileFile = profile_array[profile_index];
			}
		EditorGUILayout.EndHorizontal();
		GUI.enabled = true;
		
		EditorGUILayout.BeginHorizontal();
		ni.quitNImate = EditorGUILayout.Toggle(new GUIContent("Quit NI mate", "Send a quit signal to NI mate when the game ends"), ni.quitNImate);
		GUI.enabled = ni.quitNImate;
			ni.quitPort = EditorGUILayout.IntField(new GUIContent("Port", "NI mate will receive the quit OSC message on this port, must match the OSC input port in NI mate preferences!"), ni.quitPort);
		GUI.enabled = true;
		EditorGUILayout.EndHorizontal();
	}
}

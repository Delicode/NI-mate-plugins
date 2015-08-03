/* Original code by Delicode Ltd (www.delicode.com) */
/* All modifications are allowed, but we encourage  */
/* sharing any beneficial modifications at the NI   */
/* mate forums (forum.ni-mate.com).				    */

using UnityEngine;
using UnityEditor;

[CustomEditor(typeof(NImateFeed))]
public class NI_mate_feed_UI : Editor
{	
	public override void OnInspectorGUI () {
		NImateFeed ni = (NImateFeed) target;
		ni.feed2 = EditorGUILayout.Toggle(new GUIContent("Show feed 2", "Show feed 2 instead of feed 1"), ni.feed2);
		
		if(ni.gameObject.GetComponent("GUILayer") != null) {
			ni.tex_size = EditorGUILayout.Slider(new GUIContent("Size", "Size of the drawn GUI texture"), ni.tex_size, 0, 1);
			ni.tex_x = EditorGUILayout.Slider(new GUIContent("Position x", "Horizontal position of the drawn GUI texture"), ni.tex_x, 0, 1);
			ni.tex_y = EditorGUILayout.Slider(new GUIContent("Position y", "Vertical position of the drawn GUI texture"), ni.tex_y, 0, 1);
		}
	}
}

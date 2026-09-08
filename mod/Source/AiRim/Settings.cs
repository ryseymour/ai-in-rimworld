using UnityEngine;
using Verse;

namespace AiRim
{
    public class AiRimSettings : ModSettings
    {
        public string host = "127.0.0.1";
        public int port = 7601;
        public bool enabled = true;
        public int snapshotInterval = 250;

        public override void ExposeData()
        {
            Scribe_Values.Look(ref host, "host", "127.0.0.1");
            Scribe_Values.Look(ref port, "port", 7601);
            Scribe_Values.Look(ref enabled, "enabled", true);
            Scribe_Values.Look(ref snapshotInterval, "snapshotInterval", 250);
            base.ExposeData();
        }
    }

    public class AiRimMod : Mod
    {
        public static AiRimSettings Settings;
        public const string Version = "0.1.0";

        public AiRimMod(ModContentPack content) : base(content)
        {
            Settings = GetSettings<AiRimSettings>();
        }

        public override string SettingsCategory() => "AI in RimWorld";

        public override void DoSettingsWindowContents(Rect inRect)
        {
            var list = new Listing_Standard();
            list.Begin(inRect);
            list.CheckboxLabeled("Enabled", ref Settings.enabled);
            list.Label("Orchestrator host");
            Settings.host = list.TextEntry(Settings.host);
            list.Label($"Orchestrator port: {Settings.port}");
            string portBuf = Settings.port.ToString();
            list.TextFieldNumeric(ref Settings.port, ref portBuf, 1, 65535);
            list.Label($"Snapshot interval (ticks): {Settings.snapshotInterval}");
            string ivBuf = Settings.snapshotInterval.ToString();
            list.TextFieldNumeric(ref Settings.snapshotInterval, ref ivBuf, 60, 5000);
            list.Label(Transport.Connected ? "Status: connected" : "Status: not connected");
            list.End();
        }
    }
}

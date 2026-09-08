using Verse;

namespace AiRim
{
    /// <summary>Periodic snapshots and housekeeping. Runs on the main thread each tick.</summary>
    public class AiRimGameComponent : GameComponent
    {
        private bool saidHello;
        private bool wasConnected;

        public AiRimGameComponent(Game game) { }

        public override void FinalizeInit()
        {
            saidHello = false;
        }

        public override void GameComponentTick()
        {
            if (!AiRimMod.Settings.enabled) return;

            bool connected = Transport.Connected;
            if (connected && (!saidHello || !wasConnected))
            {
                Events.Hello();
                saidHello = true;
                SnapshotAll();
            }
            wasConnected = connected;
            if (!connected) return;

            int interval = System.Math.Max(60, AiRimMod.Settings.snapshotInterval);
            if (Find.TickManager.TicksGame % interval == 0) SnapshotAll();

            if (Find.TickManager.TicksGame % 600 == 0)
            {
                int d = Transport.TakeDropped();
                if (d > 0) Events.Dropped(d);
            }
        }

        private static void SnapshotAll()
        {
            foreach (var map in Find.Maps)
            {
                Events.WorldSnapshot(map);
                foreach (var p in map.mapPawns.AllPawnsSpawned)
                    if (Events.Tracked(p)) Events.PawnSnapshot(p);
            }
        }
    }
}

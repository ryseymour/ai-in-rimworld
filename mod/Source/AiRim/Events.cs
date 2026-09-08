using System.Collections.Generic;
using System.Text.RegularExpressions;
using System.Linq;
using RimWorld;
using Verse;
using Verse.AI;

namespace AiRim
{
    /// <summary>Builds event JSON from game objects. Main thread only.</summary>
    public static class Events
    {
        private static Json Base(string type)
        {
            int tick = Current.ProgramState == ProgramState.Playing && Find.TickManager != null ? Find.TickManager.TicksGame : 0;
            return Json.Obj().Put("v", 0).Put("t", tick).Put("type", type);
        }

        public static void Emit(Json j)
        {
            if (!AiRimMod.Settings.enabled) return;
            Transport.Send(j.ToString());
        }

        /// <summary>Run an observer; never let an observer exception reach game code.</summary>
        public static void Guard(string what, System.Action a)
        {
            try { a(); }
            catch (System.Exception e) { Log.ErrorOnce($"[AiRim] {what} failed: {e}", what.GetHashCode()); }
        }

        public static string Kind(Pawn p)
        {
            if (p.RaceProps != null && !p.RaceProps.Humanlike) return "animal";
            if (p.IsColonist) return "colonist";
            if (p.IsPrisoner) return "prisoner";
            if (p.HostileTo(Faction.OfPlayerSilentFail)) return "hostile";
            return "visitor";
        }

        public static bool Tracked(Pawn p)
        {
            if (p == null || p.Dead || !p.Spawned) return false;
            if (p.RaceProps == null || !p.RaceProps.Humanlike) return false;
            return true;
        }

        private static readonly Regex TagRx = new Regex(@"<[^>]+>|\(\*[^)]*\)|\(/[^)]*\)", RegexOptions.Compiled);

        /// <summary>Strip Unity rich-text and RimWorld (*Tag) markup from display strings.</summary>
        public static string Clean(string s) => s == null ? null : TagRx.Replace(s, "").Trim();

        public static string Name(Pawn p) => p.Name != null ? p.Name.ToStringShort : p.LabelShortCap;

        public static string JobLabel(Pawn p)
        {
            var job = p.jobs?.curJob;
            if (job == null) return null;
            try { return Clean(p.jobs.curDriver?.GetReport() ?? job.def.label).TrimEnd('.'); }
            catch { return job.def.label; }
        }

        public static void Hello()
        {
            Emit(Base("hello")
                .Put("mod_version", AiRimMod.Version)
                .Put("game_version", VersionControl.CurrentVersionStringWithRev)
                .Put("map_id", Find.CurrentMap?.uniqueID ?? -1));
        }

        public static void WorldSnapshot(Map map)
        {
            int colonists = 0, visitors = 0, hostiles = 0;
            foreach (var p in map.mapPawns.AllPawnsSpawned)
            {
                if (!Tracked(p)) continue;
                switch (Kind(p))
                {
                    case "colonist": colonists++; break;
                    case "hostile": hostiles++; break;
                    case "visitor": visitors++; break;
                }
            }
            long tile = map.Tile;
            Emit(Base("world_snapshot")
                .Put("date", GenDate.DateFullStringAt(Find.TickManager.TicksAbs, Find.WorldGrid.LongLatOf(map.Tile)))
                .Put("season", GenLocalDate.Season(map).ToString())
                .Put("weather", map.weatherManager.curWeather?.label)
                .Put("wealth", (int)map.wealthWatcher.WealthTotal)
                .Put("colonists", colonists)
                .Put("visitors", visitors)
                .Put("hostiles", hostiles)
                .Put("tile", tile));
        }

        public static void PawnSnapshot(Pawn p)
        {
            var needs = Json.Obj();
            if (p.needs != null)
            {
                if (p.needs.food != null) needs.Put("food", p.needs.food.CurLevelPercentage);
                if (p.needs.rest != null) needs.Put("rest", p.needs.rest.CurLevelPercentage);
                if (p.needs.joy != null) needs.Put("joy", p.needs.joy.CurLevelPercentage);
            }

            var thoughts = new List<Json>();
            if (p.needs?.mood?.thoughts != null)
            {
                var tmp = new List<Thought>();
                p.needs.mood.thoughts.GetAllMoodThoughts(tmp);
                foreach (var t in tmp.OrderByDescending(t => System.Math.Abs(t.MoodOffset())).Take(6))
                    thoughts.Add(Json.Obj().Put("label", Clean(t.LabelCap.ToString())).Put("mood", (int)t.MoodOffset()));
            }

            var skills = Json.Obj();
            if (p.skills != null)
                foreach (var s in p.skills.skills)
                    if (!s.TotallyDisabled) skills.Put(s.def.defName, s.Level);

            var relations = new List<Json>();
            if (p.relations != null)
            {
                foreach (var other in p.relations.RelatedPawns.Take(8))
                {
                    var rel = p.GetMostImportantRelation(other);
                    relations.Add(Json.Obj()
                        .Put("other", Name(other))
                        .Put("kind", rel?.label ?? "related")
                        .Put("opinion", p.relations.OpinionOf(other)));
                }
            }

            var pos = p.Position;
            Emit(Base("pawn_snapshot")
                .Put("id", p.thingIDNumber)
                .Put("name", Name(p))
                .Put("faction", p.Faction?.Name)
                .Put("kind", Kind(p))
                .PutInts("pos", pos.x, pos.y, pos.z)
                .Put("job", JobLabel(p))
                .Put("needs", needs)
                .Put("mood", p.needs?.mood != null ? p.needs.mood.CurLevelPercentage : float.NaN)
                .PutObjects("thoughts", thoughts)
                .Put("health", p.health?.summaryHealth != null ? HealthUtility.GetGeneralConditionLabel(p, true) : null)
                .Put("skills", skills)
                .PutStrings("traits", p.story?.traits?.allTraits.Select(t => t.LabelCap) ?? Enumerable.Empty<string>())
                .PutObjects("relations", relations)
                .Put("drafted", p.Drafted));
        }

        public static void JobStart(Pawn p, Job job)
        {
            if (!Tracked(p) || job == null) return;
            Emit(Base("job_start")
                .Put("pawn", p.thingIDNumber)
                .Put("job", job.def.defName)
                .Put("target", job.targetA.IsValid ? job.targetA.ToString() : null)
                .Put("source", job.jobGiver?.GetType().Name ?? job.workGiverDef?.defName));
        }

        public static void JobEnd(Pawn p, Job job, JobCondition condition)
        {
            if (!Tracked(p) || job == null) return;
            Emit(Base("job_end")
                .Put("pawn", p.thingIDNumber)
                .Put("job", job.def.defName)
                .Put("condition", condition.ToString()));
        }

        public static void Interaction(PlayLogEntry_Interaction entry, Pawn initiator, Pawn recipient, InteractionDef def)
        {
            Emit(Base("interaction")
                .Put("initiator", initiator?.thingIDNumber ?? -1)
                .Put("recipient", recipient?.thingIDNumber ?? -1)
                .Put("def", def?.defName)
                .Put("text", SafeText(entry, initiator)));
        }

        private static string SafeText(LogEntry entry, Pawn pov)
        {
            try { return Clean(entry.ToGameStringFromPOV(pov, false)); }
            catch { return null; }
        }

        public static void MentalState(Pawn p, MentalStateDef def, string reason)
        {
            if (!Tracked(p)) return;
            Emit(Base("mental_state").Put("pawn", p.thingIDNumber).Put("state", def?.label).Put("reason", reason));
        }

        public static void Hediff(Pawn p, Verse.Hediff h)
        {
            if (!Tracked(p) || h == null) return;
            if (h.def.isBad == false && h.def.everCurableByItem == false && h.Severity < 0.1f) return;
            Emit(Base("hediff")
                .Put("pawn", p.thingIDNumber)
                .Put("def", h.def.defName)
                .Put("part", h.Part?.Label)
                .Put("severity", h.Severity));
        }

        public static void Death(Pawn p, DamageInfo? dinfo)
        {
            if (p == null || p.RaceProps == null || !p.RaceProps.Humanlike) return;
            Emit(Base("death")
                .Put("pawn", p.thingIDNumber)
                .Put("cause", dinfo?.Def?.defName)
                .Put("killer", dinfo?.Instigator is Pawn k ? Name(k) : dinfo?.Instigator?.LabelShort));
        }

        public static void Letter(Verse.Letter letter)
        {
            if (letter == null) return;
            string text = null;
            if (letter is ChoiceLetter cl) text = Clean(cl.Text.ToString());
            Emit(Base("letter").Put("label", Clean(letter.Label.ToString())).Put("text", text).Put("def", letter.def?.defName));
        }

        public static void Incident(IncidentDef def, IncidentParms parms, bool fired)
        {
            if (!fired || def == null) return;
            Emit(Base("incident").Put("def", def.defName).Put("label", def.label).Put("points", parms?.points ?? 0f));
        }

        public static void Dropped(int n) => Emit(Base("dropped").Put("count", n));
    }
}

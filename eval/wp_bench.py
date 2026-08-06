"""Win Probability bench — canned NCAA scenarios."""
import json
from qoresence.agents.win_probability import FootballWinProbability

SCENARIOS = [
    {"name":"blowout early","quarter":1,"clock_seconds":800,"down":1,"yards_to_go":10,"field_position":"own 25","home_score":28,"away_score":0,"possession":"home"},
    {"name":"close late redzone","quarter":4,"clock_seconds":45,"down":2,"yards_to_go":3,"field_position":"opp 8","home_score":21,"away_score":24,"possession":"home"},
    {"name":"OT tied","quarter":5,"clock_seconds":900,"down":1,"yards_to_go":10,"field_position":"opp 25","home_score":28,"away_score":28,"possession":"home"},
    {"name":"end half dampen","quarter":2,"clock_seconds":60,"down":1,"yards_to_go":10,"field_position":"own 40","home_score":14,"away_score":17,"possession":"away"},
    {"name":"4th and inches","quarter":4,"clock_seconds":120,"down":4,"yards_to_go":1,"field_position":"opp 2","home_score":17,"away_score":17,"possession":"home"},
]

def main():
    wp=FootballWinProbability()
    rows=[]
    for s in SCENARIOS:
        wp.reset()
        r=wp.compute(s)
        rows.append({"scenario":s["name"],"win_prob":round(r["win_prob"],3),"ep":round(r["expected_points"],2),"yds_to_opp":r["yds_to_opp"]})
        print(f"{s['name']:20} wp={r['win_prob']:.3f} ep={r['expected_points']:.1f} yds={r['yds_to_opp']}")
    # clip worthiness quick
    try:
        from qoresence.agents.moment_scorer import ClipWorthinessModel
        m=ClipWorthinessModel()
        print("clip demo:", round(m.predict({"wp_swing":0.15,"red_zone":1,"close_game":1,"apm":0.7}),3))
    except Exception as e:
        print("clip demo skip:",e)
    return rows

if __name__=="__main__":
    print(json.dumps(main(),indent=2))

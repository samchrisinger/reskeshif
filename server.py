from flask import Flask, request, jsonify, redirect, url_for
from pyelasticsearch import ElasticSearch
import json
import os
import sys

app = Flask(__name__, static_url_path='')
app.debug = True

es = ElasticSearch('http://localhost:9200')

schema_cache = None
map_cache = None

def get_map():
    global es
    global map_cache
    if map_cache:
        return map_cache
    else:
        query = {
            "query": {
                "match_all": {}
            },
            "size": 1
        }
        res = es.search(query, index='test')
        mp = res['hits']['hits'][0]['_source']['map']        
        map_cache = mp
        return mp

def get_schema():
    global es
    global schema_cache
    if schema_cache:
        return schema_cache
    schema = {}
    d_map = get_map()
    aggs = {}
    keys = [key for key in d_map.keys() if d_map[key]['type'] == 'string']
    for key in keys:
        bucket = key+'_bucket'       
        aggs[bucket] = {"terms": {"field": key}}
        
    query = {
        "aggs" : aggs
    }
        
    res = es.search(query, index='test')
    aggs = res['aggregations']
    for key in keys:                
        buckets = aggs[key+'_bucket']['buckets']
        schema[key] = {
            'type': 'string',
            'categories': [b['key'] for b in buckets]
        }

    keys = [key for key in d_map.keys() if d_map[key]['type'] == 'date']
    aggs = {}
    for key in keys:
        aggs['max_'+key] = {"max": {"field": key}}
        aggs['min_'+key] = {"min": {"field": key}}
    
    res = es.search({"aggs":aggs}, index='test')
    aggs = res['aggregations']
    for key in keys:
        schema[key] = {
            'type': 'date',
            'max': aggs['max_'+key]['value'],
            'min': aggs['min_'+key]['value'],
        }
    schema_cache = schema
    return schema

@app.route('/')
def root():
    return redirect(url_for('static', filename='app.html'))

@app.route('/times')
def times():
    global es    
    page = request.args.get('page') or 0
    page = int(page)
    schema = get_schema()
    keys = [k for k in schema.keys() if schema[k]['type'] == 'date']
    sub_schema = {}
    for k in keys:
        sub_schema[k] = schema[k]
    query = {
        "query" : {
            "match_all" : {}
        },
        "partial_fields" : {
            "dates": {
                "include" :  keys
            }
        },
        "from": (page*1000),
        "size": 1000
    }
    res = es.search(query, index='test')
    times = [h['fields']['dates'][0] for h in res['hits']['hits']]    
    maxes = [sub_schema[key]['max'] for key in sub_schema.keys()]
    mins = [sub_schema[key]['min'] for key in sub_schema.keys()]    
    gtime = {'max': max(maxes), 'min': min(mins)}
    sub_schema['__global'] = gtime
    return jsonify({
        'times': times,
        'schema': sub_schema
    })
    

@app.route('/search')
def search():
    global es
    args = request.args
    query = None
    if args.get('query'):
        query = json.loads(args.get('query'))
        query['size'] = 100
    else:
        query = {
            "query": {
                "match_all": {}
            },
            "size": 100
        }
    res = es.search(query, index="test")
    hits = [h['_source'] for h in res['hits']['hits']]

    if args.get('query'):        
        for hit in hits:
            del hit['map']
        return jsonify({
            'size': res['hits']['total'],
            'data': hits
        })

    schema = get_schema()
        
    for hit in hits:
        del hit['map']
    return jsonify({
        'size': res['hits']['total'],
        'data': hits,
        'schema': schema
    })
        
@app.route('/js/<path:path>')
def static_proxy(path):
    return app.send_static_file(os.path.join('js', path))

if __name__ == '__main__':
    app.run()
